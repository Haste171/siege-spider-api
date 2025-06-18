from collections import defaultdict
from database.handler import get_db
from database.models import SiegeBan, SiegeBanMetadata, Match
from fastapi import HTTPException, Depends, Request, APIRouter
from itertools import combinations
from pydantic import BaseModel, Field
from services.user.token import get_current_user
from services.webhook_exception_handler import WebhookExceptionHandler
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from wrapper.models import Player
import logging
import math

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
router = APIRouter()

@router.get("/lookup/uplay/{uplay}")
async def lookup_profile_id(request: Request, uplay: str, current_user = Depends(get_current_user)):
    try:
        ubisoft_handler = request.app.state.ubisoft_handler

        player: Player = await ubisoft_handler.lookup_via_uplay(uplay)

        return ubisoft_handler.format_player(player)
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Uplay Lookup: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Uplay Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/bans/{uplay}/uplay")
async def lookup_bans_uplay(request: Request, uplay: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        bans = db.query(SiegeBan).filter(SiegeBan.uplay.ilike(uplay.lower())).all()
        if not bans or len(bans) == 0:
            return HTTPException(status_code=404, detail="No bans found for the provided uplay username.")
        return {"bans": bans}
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Uplay Ban Lookup]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Uplay Ban Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/bans/{uplay}/uplay/metadata")
async def lookup_bans_metadata_uplay(request: Request, uplay: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        # Query the SiegeBans table to retrieve the ban ID(s) for the given Uplay username.
        ban_ids = db.query(SiegeBan.id).filter(SiegeBan.uplay.ilike(uplay.lower())).all()

        if not ban_ids:
            return HTTPException(status_code=404, detail="No bans found for the provided Uplay username.")
        # Extract the Ban IDs from the result
        ban_ids = [ban_id[0] for ban_id in ban_ids]
        # Query the SiegeBanMetadata table to retrieve metadata for the retrieved Ban IDs.
        metadata = db.query(SiegeBanMetadata).filter(SiegeBanMetadata.ban_id.in_(ban_ids)).all()
        if not metadata:
            return HTTPException(status_code=404, detail="No metadata found for the provided Uplay username.")
        return {"metadata": metadata}
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Uplay Ban Metadata Lookup]: {e}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Uplay Ban Metadata Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/profile_id/{profile_id}")
async def lookup_profile_id(request: Request, profile_id: str, current_user = Depends(get_current_user)):
    try:
        ubisoft_handler = request.app.state.ubisoft_handler

        player: Player = await ubisoft_handler.lookup_via_profile_id(profile_id)

        return ubisoft_handler.format_player(player)
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Profile ID Lookup]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Profile ID Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/bans/{profile_id}/profile_id")
async def lookup_bans_profile_id(request: Request, profile_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        # Clean up profile_id (e.g., remove spaces, ensure proper matching) -- avoids wildcards
        profile_id = profile_id.strip()

        # Query the database using ilike (case-insensitive comparison)
        bans = db.query(SiegeBan).filter(SiegeBan.profile_id.ilike(profile_id)).all()

        # If no bans are found, raise 404 exception
        if not bans or len(bans) == 0:
            return HTTPException(
                status_code=404,
                detail=f"No bans found for the provided profile ID: {profile_id}"
            )

        # Return results
        return {"bans": bans}
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Unexpected error occurred: {e}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Profile ID Ban Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/bans/{profile_id}/profile_id/metadata")
async def lookup_bans_metadata_profile_id(request: Request, profile_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        # will need to get ban id from siege bans table then use that id to get corresponding metadata:
        # Query the SiegeBans table to retrieve the ban ID(s) for the given profile ID.
        ban_ids = db.query(SiegeBan.id).filter(SiegeBan.profile_id.ilike(profile_id)).all()

        if not ban_ids:
            return HTTPException(status_code=404, detail="No bans found for the provided profile ID.")
        # Extract the Ban IDs from the result
        ban_ids = [ban_id[0] for ban_id in ban_ids]
        # Query the SiegeBanMetadata table to retrieve metadata for the retrieved Ban IDs.
        metadata = db.query(SiegeBanMetadata).filter(SiegeBanMetadata.ban_id.in_(ban_ids)).all()
        if not metadata:
            return HTTPException(status_code=404, detail="No metadata found for the provided profile ID.")
        return {"metadata": metadata}
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Profile ID Ban Metadata Lookup]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Profile ID Ban Metadata Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

class MatchLookupModel(BaseModel):
    match_id: str

@router.post("/lookup/match")
async def lookup_match_players(
        request: Request,
        data: MatchLookupModel,
        db: Session = Depends(get_db)
):
    try:
        match = db.query(Match).filter(Match.id == data.match_id).first()
        if not match:
            raise HTTPException(status_code=404, detail="No match found for the provided match ID!")

        ubisoft_handler = request.app.state.ubisoft_handler
        players = []
        for item in match.teams:
            for key, value in item.items():
                player: Player = await ubisoft_handler.lookup_via_profile_id(key)
                data_to_add = ubisoft_handler.format_player(player)
                data_to_add["team"] = value
                players.append(data_to_add)
        return players
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Match Lookup]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Match Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

def get_player_connections_simple(session: Session, match_id: str, min_matches_together: int = 3) -> Dict[str, Any]:
    """
    Simplified version that just returns player IDs grouped by who plays together.
    Perfect for UI display.
    """
    result = find_player_groups(session, match_id, min_matches_together)

    if "error" in result:
        return result

    return {
        "match_id": match_id,
        "team_0_groups": [group["players"] for group in result["team_0"]["groups"]],
        "team_1_groups": [group["players"] for group in result["team_1"]["groups"]]
    }


def find_player_groups(session: Session, match_id: str, min_matches_together: int) -> Dict[str, Any]:
    """
    Find groups of players who frequently play together in a specific match.
    """
    # Get the specific match
    target_match = session.query(Match).filter(Match.id == match_id).first()
    if not target_match:
        return {"error": f"Match with ID {match_id} not found"}

    # Parse teams from the target match
    teams_data = target_match.teams
    team_0_players = []
    team_1_players = []

    for player_dict in teams_data:
        for player_id, team in player_dict.items():
            if team == 0:
                team_0_players.append(player_id)
            elif team == 1:
                team_1_players.append(player_id)

    # Find groups for each team
    team_0_groups = find_frequent_groups(session, team_0_players, 0, min_matches_together)
    team_1_groups = find_frequent_groups(session, team_1_players, 1, min_matches_together)

    return {
        "match_id": match_id,
        "team_0": {
            "players": team_0_players,
            "groups": team_0_groups
        },
        "team_1": {
            "players": team_1_players,
            "groups": team_1_groups
        }
    }


def find_frequent_groups(session: Session, team_players: List[str], team_number: int, min_matches_together: int) -> List[Dict[str, Any]]:
    """
    Find all groups of players who have played together frequently.
    Uses connected components to merge groups that share players.
    """
    if len(team_players) < 2:
        return []

    # Get all matches from database
    all_matches = session.query(Match).all()

    # Build a graph of player connections
    player_connections = defaultdict(lambda: defaultdict(int))

    for match in all_matches:
        match_teams = match.teams
        match_players_on_team = set()

        # Extract players on the same team number from this match
        for player_dict in match_teams:
            for player_id, team in player_dict.items():
                if team == team_number and player_id in team_players:
                    match_players_on_team.add(player_id)

        # Count connections between all pairs of players in this match
        if len(match_players_on_team) >= 2:
            for p1, p2 in combinations(sorted(match_players_on_team), 2):
                player_connections[p1][p2] += 1
                player_connections[p2][p1] += 1

    # Find connected components using Union-Find
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Union players who have played together >= min_matches_together times
    for player in team_players:
        find(player)  # Initialize parent

    for player, connections in player_connections.items():
        for connected_player, match_count in connections.items():
            if match_count >= min_matches_together:
                union(player, connected_player)

    # Group players by their root parent (connected component)
    groups = defaultdict(list)
    for player in team_players:
        root = find(player)
        groups[root].append(player)

    # Convert to final format, only including groups with 2+ players
    frequent_groups = []
    for root, players in groups.items():
        if len(players) >= 2:
            # Calculate the minimum match count for this group
            min_group_matches = float('inf')
            for p1, p2 in combinations(players, 2):
                match_count = player_connections[p1][p2]
                if match_count > 0:
                    min_group_matches = min(min_group_matches, match_count)

            if min_group_matches == float('inf'):
                min_group_matches = 0

            frequent_groups.append({
                "players": sorted(players),
                "matches_together": int(min_group_matches)
            })

    return frequent_groups


@router.post("/lookup/match/team_relationships")
async def lookup_match_players(
        request: Request,
        data: MatchLookupModel,
        db: Session = Depends(get_db)
):
    try:
        # Get the team relationships
        relationships = get_player_connections_simple(
            db,
            data.match_id,
            3
        )

        if "error" in relationships:
            raise HTTPException(status_code=404, detail=relationships["error"])

        # Return the relationships
        return {
            "success": True,
            "data": relationships
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


class PlayerMatchesLookupModel(BaseModel):
    """Request model for player matches lookup with pagination."""
    profile_id: str = Field(..., description="The player's profile ID")
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=10, ge=1, le=100, description="Number of matches per page")


def get_player_matches_with_summary(session: Session, profile_id: str, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
    """
    Retrieve all matches for a specific player with pagination and summary statistics.

    Args:
        session: Database session
        profile_id: The player's profile ID to search for
        page: Page number (1-indexed)
        page_size: Number of matches per page

    Returns:
        Dictionary containing paginated match data, summary statistics, and metadata
    """
    try:
        # For PostgreSQL JSONB, we can use containment operators or filter in Python
        # Get all matches where teams is not null
        all_matches = (
            session.query(Match)
            .filter(Match.teams.isnot(None))
            .order_by(Match.created_at.desc()) 
            .all()
        )
        matching_matches = []

        for match in all_matches:
            teams_data = match.teams
            player_found = False

            # Search through the teams structure to find the profile_id
            if teams_data and isinstance(teams_data, list):
                for player_dict in teams_data:
                    if isinstance(player_dict, dict) and profile_id in player_dict:
                        player_found = True
                        break

            if player_found:
                matching_matches.append(match)

        # Calculate pagination values
        total_matches = len(matching_matches)
        total_pages = math.ceil(total_matches / page_size) if total_matches > 0 else 1
        offset = (page - 1) * page_size

        # Validate page number
        if page > total_pages and total_matches > 0:
            return {
                "error": f"Page {page} does not exist. Total pages: {total_pages}"
            }

        # Get the paginated slice
        paginated_matches = matching_matches[offset:offset + page_size]

        # Process all matches to calculate summary statistics and format data
        all_matches_data = []
        team_0_count = 0
        team_1_count = 0
        wins = 0
        losses = 0

        for match in matching_matches:
            # Determine which team the player was on
            player_team = None
            teams_data = match.teams

            if teams_data and isinstance(teams_data, list):
                for player_dict in teams_data:
                    if isinstance(player_dict, dict) and profile_id in player_dict:
                        player_team = player_dict[profile_id]
                        break

            # Count team distribution
            if player_team == 0:
                team_0_count += 1
            elif player_team == 1:
                team_1_count += 1

            # Count wins and losses
            if hasattr(match, 'winner') and match.winner is not None:
                if match.winner == player_team:
                    wins += 1
                else:
                    losses += 1

            match_data = {
                "match_id": match.id,
                "player_team": player_team,
                "created_at": match.created_at.isoformat() if hasattr(match, 'created_at') and match.created_at else None,
                "teams": teams_data
            }

            # Add any other relevant match fields
            if hasattr(match, 'status'):
                match_data["status"] = match.status
            if hasattr(match, 'duration'):
                match_data["duration"] = match.duration
            if hasattr(match, 'winner'):
                match_data["winner"] = match.winner

            all_matches_data.append(match_data)

        # Get paginated slice for current page
        paginated_matches = all_matches_data[offset:offset + page_size]

        # Calculate win rate
        win_rate = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0.0

        return {
            "profile_id": profile_id,
            "matches": paginated_matches,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_matches": total_matches,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1
            },
            "summary": {
                "total_matches": total_matches,
                "team_0_matches": team_0_count,
                "team_1_matches": team_1_count,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 2)
            }
        }

    except Exception as e:
        return {"error": f"Database error: {str(e)}"}


@router.post("/lookup/matches/profile_id")
async def lookup_player_matches(
        request: Request,
        data: PlayerMatchesLookupModel,
        db: Session = Depends(get_db)
):
    """
    Retrieve all matches played by a specific player with pagination and summary statistics.

    This endpoint searches through the match database to find all games
    where the specified profile ID participated, returning paginated match results
    along with comprehensive summary statistics including wins, losses, team
    distribution, and win rate calculations.
    """
    try:
        # Validate input
        if not data.profile_id.strip():
            raise HTTPException(status_code=400, detail="Profile ID cannot be empty")

        # Get the player's matches with summary statistics
        result = get_player_matches_with_summary(
            db,
            data.profile_id.strip(),
            data.page,
            data.page_size
        )

        if "error" in result:
            if "does not exist" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=500, detail=result["error"])

        # Return the paginated results with summary statistics
        return {
            "success": True,
            "data": result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

class PlayerNameMatchesLookupModel(BaseModel):
    """Request model for player matches lookup with pagination."""
    name: str = Field(..., description="The player's profile uplay username")
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=10, ge=1, le=100, description="Number of matches per page")

@router.post("/lookup/matches/name")
async def lookup_player_matches(
        request: Request,
        data: PlayerNameMatchesLookupModel,
        db: Session = Depends(get_db)
):
    """
    Retrieve all matches played by a specific player with pagination and summary statistics.

    This endpoint searches through the match database to find all games
    where the specified profile ID participated, returning paginated match results
    along with comprehensive summary statistics including wins, losses, team
    distribution, and win rate calculations.
    """
    try:
        # Validate input
        if not data.name.strip():
            raise HTTPException(status_code=400, detail="Name cannot be empty")

        ubisoft_handler = request.app.state.ubisoft_handler

        player: Player = await ubisoft_handler.lookup_via_uplay(data.name.strip())

        # Get the player's matches with summary statistics
        result = get_player_matches_with_summary(
            db,
            player.uid,
            data.page,
            data.page_size
        )

        if "error" in result:
            if "does not exist" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=500, detail=result["error"])

        # Return the paginated results with summary statistics
        return {
            "success": True,
            "data": result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/bans")
async def get_all_bans(
        request: Request,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user),
        page: int = 1,
        limit: int = 25,
):
    try:
        # Calculate offset based on page and limit
        offset = (page - 1) * limit

        # Get total count for pagination info
        total_bans = db.query(SiegeBan).count()

        # Get paginated bans
        bans = db.query(SiegeBan).offset(offset).limit(limit).all()

        # If no bans are found, return empty list but not an error
        if not bans:
            return {
                "bans": [],
                "pagination": {
                    "total": total_bans,
                    "page": page,
                    "limit": limit,
                    "pages": (total_bans + limit - 1) // limit  # Ceiling division
                }
            }

        return {
            "bans": bans,
            "pagination": {
                "total": total_bans,
                "page": page,
                "limit": limit,
                "pages": (total_bans + limit - 1) // limit  # Ceiling division
            }
        }
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Get All Bans]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Get All Bans]",
            e_str=e_str
        )
        raise Exception(e_str)
