"""
Data fetching and extraction for LivePlayerStats plugin.

Handles ESPN API integration and extraction of stat leaders for
basketball (NBA/NCAAM) and football (NFL/NCAAF) games.
"""

from typing import Dict, List, Optional
from datetime import datetime


# ESPN API league mapping
LEAGUE_MAP = {
    'nba': ('basketball', 'nba'),
    'nfl': ('football', 'nfl'),
    'ncaam': ('basketball', 'mens-college-basketball'),
    'ncaaf': ('football', 'college-football')
}

# Basketball stat array indices (from ESPN API)
BASKETBALL_STAT_INDICES = {
    'PTS': 15,  # Points
    'REB': 10,  # Rebounds
    'AST': 11   # Assists
}


class DataFetcher:
    """Fetches and extracts player statistics from ESPN API."""

    def __init__(self, api_helper, cache_manager, logger):
        """
        Initialize data fetcher.

        Args:
            api_helper: APIHelper instance for ESPN requests
            cache_manager: CacheManager for data caching
            logger: Logger instance
        """
        self.api_helper = api_helper
        self.cache_manager = cache_manager
        self.logger = logger

    def fetch_live_games(self, league_key: str, max_games: int = 50) -> List[Dict]:
        """
        Fetch live games for a specific league.

        Args:
            league_key: League identifier ('nba', 'nfl', 'ncaam', 'ncaaf')
            max_games: Maximum number of games to return

        Returns:
            List of game dictionaries with extracted stats
        """
        if league_key not in LEAGUE_MAP:
            self.logger.warning(f"Unknown league: {league_key}")
            return []

        sport, league = LEAGUE_MAP[league_key]

        # Create cache key with current date
        date_str = datetime.now().strftime('%Y%m%d')
        cache_key = f"live_stats_{league_key}_{date_str}"

        try:
            # Fetch scoreboard with 60-second cache for live updates
            scoreboard = self.api_helper.fetch_espn_scoreboard(
                sport=sport,
                league=league,
                cache_key=cache_key,
                cache_ttl=60
            )

            if not scoreboard or 'events' not in scoreboard:
                self.logger.debug(f"No scoreboard data for {league_key}")
                return []

            # Extract live games
            live_games = []
            total_events = len(scoreboard.get('events', []))
            self.logger.debug(f"Processing {total_events} total events for {league_key}")

            for event in scoreboard.get('events', []):
                # Stop if we've reached max games
                if len(live_games) >= max_games:
                    self.logger.info(f"Reached max_games limit ({max_games}) for {league_key}")
                    break

                # Only process games that are live (in progress)
                status_state = event.get('status', {}).get('type', {}).get('state')
                self.logger.debug(f"Event status: {status_state}")

                if status_state != 'in':
                    continue

                # Parse game event
                game_info = self._parse_game_event(event, league_key)
                if game_info:
                    live_games.append(game_info)
                    self.logger.info(f"Parsed live game: {game_info.get('away_abbr')} @ {game_info.get('home_abbr')}, "
                                   f"home_leaders: {bool(game_info.get('home_leaders'))}, "
                                   f"away_leaders: {bool(game_info.get('away_leaders'))}")

            self.logger.info(f"Found {len(live_games)} live games in {league_key} (out of {total_events} total, max={max_games})")
            return live_games

        except Exception as e:
            self.logger.error(f"Error fetching live games for {league_key}: {e}", exc_info=True)
            return []

    def _parse_game_event(self, event: Dict, league_key: str) -> Optional[Dict]:
        """
        Parse a game event and extract relevant information.

        Args:
            event: ESPN API event dictionary
            league_key: League identifier for sport-specific parsing

        Returns:
            Dictionary with game info and stat leaders, or None if parsing fails
        """
        try:
            competition = event.get('competitions', [{}])[0]
            status = event.get('status', {})
            competitors = competition.get('competitors', [])
            game_id = event.get('id')

            if len(competitors) < 2:
                return None

            # Identify home and away teams
            home_team = next((c for c in competitors if c.get('homeAway') == 'home'), None)
            away_team = next((c for c in competitors if c.get('homeAway') == 'away'), None)

            if not home_team or not away_team:
                return None

            # Extract basic game info
            game_data = {
                'id': game_id,
                'home_abbr': home_team.get('team', {}).get('abbreviation', 'HOME'),
                'away_abbr': away_team.get('team', {}).get('abbreviation', 'AWAY'),
                'home_score': int(home_team.get('score', 0)),
                'away_score': int(away_team.get('score', 0)),
                'period': status.get('period', 0),
                'clock': status.get('displayClock', ''),
                'period_text': status.get('type', {}).get('shortDetail', ''),
            }

            # Fetch detailed boxscore for player stats
            if game_id:
                boxscore = self._fetch_game_boxscore(game_id, league_key)
                if boxscore:
                    # Extract stat leaders from boxscore
                    if league_key in ['nba', 'ncaam']:
                        game_data['home_leaders'] = self._extract_boxscore_basketball_leaders(boxscore, 'home')
                        game_data['away_leaders'] = self._extract_boxscore_basketball_leaders(boxscore, 'away')
                    elif league_key in ['nfl', 'ncaaf']:
                        game_data['home_leaders'] = self._extract_boxscore_football_leaders(boxscore, 'home')
                        game_data['away_leaders'] = self._extract_boxscore_football_leaders(boxscore, 'away')
                else:
                    # Fallback to scoreboard data (will likely be None)
                    if league_key in ['nba', 'ncaam']:
                        game_data['home_leaders'] = self.extract_basketball_leaders(home_team)
                        game_data['away_leaders'] = self.extract_basketball_leaders(away_team)
                    elif league_key in ['nfl', 'ncaaf']:
                        game_data['home_leaders'] = self.extract_football_leaders(home_team)
                        game_data['away_leaders'] = self.extract_football_leaders(away_team)

            return game_data

        except Exception as e:
            self.logger.warning(f"Error parsing game event: {e}")
            return None

    def _fetch_game_boxscore(self, game_id: str, league_key: str) -> Optional[Dict]:
        """
        Fetch detailed boxscore for a specific game.

        Args:
            game_id: ESPN game ID
            league_key: League identifier

        Returns:
            Boxscore data or None if unavailable
        """
        sport, league = LEAGUE_MAP.get(league_key, (None, None))
        if not sport or not league:
            return None

        try:
            # ESPN boxscore/summary endpoint
            url = f"https://site.web.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary"
            params = {'event': game_id}
            cache_key = f"boxscore_{league_key}_{game_id}"

            response = self.api_helper.get(
                url,
                params=params,
                cache_key=cache_key,
                cache_ttl=60
            )

            return response

        except Exception as e:
            self.logger.debug(f"Error fetching boxscore for game {game_id}: {e}")
            return None

    def _extract_boxscore_basketball_leaders(self, boxscore: Dict, home_away: str) -> Optional[Dict]:
        """
        Extract basketball leaders from boxscore data.

        Args:
            boxscore: Boxscore response from ESPN
            home_away: 'home' or 'away'

        Returns:
            Leaders dict or None
        """
        try:
            # Navigate boxscore structure
            # Boxscore typically has: boxscore.players array with team data
            players_section = boxscore.get('boxscore', {}).get('players', [])

            # Find the team (home is usually index 1, away is 0, but check homeAway field)
            team_data = None
            for team in players_section:
                team_info = team.get('team', {})
                if team_info.get('homeAway') == home_away:
                    team_data = team
                    break

            if not team_data:
                self.logger.debug(f"No team data found for {home_away} in boxscore")
                return None

            # Get statistics from players
            statistics = team_data.get('statistics', [])
            if not statistics:
                return None

            # Find the main stats section (usually first one with athletes)
            stats_group = statistics[0] if statistics else None
            if not stats_group:
                return None

            athletes = stats_group.get('athletes', [])
            if not athletes:
                return None

            # Extract leaders for PTS, REB, AST
            leaders = {}
            max_pts = {'name': None, 'value': 0}
            max_reb = {'name': None, 'value': 0}
            max_ast = {'name': None, 'value': 0}

            for athlete in athletes:
                name = athlete.get('athlete', {}).get('shortName', athlete.get('athlete', {}).get('displayName', 'Unknown'))
                stats = athlete.get('stats', [])

                # Stats are usually strings in order, need to find PTS/REB/AST
                # Common order: MIN, FG, 3PT, FT, OREB, DREB, REB, AST, STL, BLK, TO, PF, PTS
                # But this varies, so we need to check the labels
                if len(stats) >= 13:  # Typical basketball stat line length
                    try:
                        pts = int(stats[-1]) if stats[-1] else 0  # PTS usually last
                        reb = int(stats[6]) if len(stats) > 6 and stats[6] else 0  # REB usually index 6
                        ast = int(stats[7]) if len(stats) > 7 and stats[7] else 0  # AST usually index 7

                        if pts > max_pts['value']:
                            max_pts = {'name': name, 'value': pts}
                        if reb > max_reb['value']:
                            max_reb = {'name': name, 'value': reb}
                        if ast > max_ast['value']:
                            max_ast = {'name': name, 'value': ast}
                    except (ValueError, IndexError):
                        continue

            if max_pts['name']:
                leaders['PTS'] = max_pts
            if max_reb['name']:
                leaders['REB'] = max_reb
            if max_ast['name']:
                leaders['AST'] = max_ast

            return leaders if leaders else None

        except Exception as e:
            self.logger.debug(f"Error extracting basketball leaders from boxscore: {e}")
            return None

    def _extract_boxscore_football_leaders(self, boxscore: Dict, home_away: str) -> Optional[Dict]:
        """
        Extract football leaders from boxscore data.

        Args:
            boxscore: Boxscore response from ESPN
            home_away: 'home' or 'away'

        Returns:
            Leaders dict or None
        """
        # Similar structure to basketball, but look for passing/rushing/receiving stats
        # Implementation similar to _extract_boxscore_basketball_leaders
        # For now, return None as football structure may differ
        return None

    def extract_basketball_leaders(self, competitor_data: Dict) -> Optional[Dict]:
        """
        Extract basketball stat leaders from competitor data.

        Finds the top player for PTS, REB, and AST.

        Args:
            competitor_data: Competitor dictionary from ESPN API

        Returns:
            Dictionary with stat leaders {'PTS': {'name': 'L. James', 'value': 24}, ...}
            or None if stats unavailable
        """
        try:
            stats_section = competitor_data.get('statistics', [])
            if not stats_section:
                self.logger.debug(f"No statistics section found for competitor")
                return None

            # Log what stat sections are available
            section_names = [s.get('name') for s in stats_section if isinstance(s, dict)]
            self.logger.debug(f"Available stat sections: {section_names}")

            # Find athletes section
            athletes_data = next((s for s in stats_section if s.get('name') == 'athletes'), None)
            if not athletes_data or 'athletes' not in athletes_data:
                self.logger.debug(f"No athletes section found. Stats structure: {stats_section[:1] if stats_section else 'empty'}")
                return None

            athletes = athletes_data.get('athletes', [])
            if not athletes:
                return None

            leaders = {}

            # Find leader for each stat category
            for stat_type, stat_index in BASKETBALL_STAT_INDICES.items():
                max_value = 0
                top_player = None

                for athlete in athletes:
                    try:
                        stats = athlete.get('stats', [])
                        if len(stats) > stat_index:
                            value = int(stats[stat_index])
                            if value > max_value:
                                max_value = value
                                # Use shortName if available, otherwise displayName
                                athlete_info = athlete.get('athlete', {})
                                top_player = athlete_info.get('shortName',
                                            athlete_info.get('displayName', 'Unknown'))
                    except (ValueError, TypeError, IndexError):
                        continue

                if top_player and max_value > 0:
                    leaders[stat_type] = {
                        'name': top_player,
                        'value': max_value
                    }

            return leaders if leaders else None

        except Exception as e:
            self.logger.debug(f"Error extracting basketball leaders: {e}")
            return None

    def extract_football_leaders(self, competitor_data: Dict) -> Optional[Dict]:
        """
        Extract football stat leaders from competitor data.

        Finds the leading QB (passing), WR (receiving), and RB (rushing).

        Args:
            competitor_data: Competitor dictionary from ESPN API

        Returns:
            Dictionary with stat leaders {'QB': {'name': 'Mahomes', 'stats': '245 YDS, 3 TD'}, ...}
            or None if stats unavailable
        """
        try:
            stats_section = competitor_data.get('statistics', [])
            if not stats_section:
                return None

            leaders = {}

            # Extract QB (top passer)
            passing_data = next((s for s in stats_section if s.get('name') == 'passing'), None)
            if passing_data and passing_data.get('athletes'):
                qb = passing_data['athletes'][0]  # Top passer
                qb_stats = qb.get('stats', [])
                if len(qb_stats) >= 4:
                    try:
                        yds = qb_stats[2]  # Passing yards
                        tds = qb_stats[3]  # Passing TDs
                        athlete_info = qb.get('athlete', {})
                        qb_name = self._abbreviate_name(
                            athlete_info.get('displayName', 'Unknown')
                        )
                        leaders['QB'] = {
                            'name': qb_name,
                            'stats': f"{yds} YDS, {tds} TD"
                        }
                    except (ValueError, IndexError):
                        pass

            # Extract WR (top receiver)
            receiving_data = next((s for s in stats_section if s.get('name') == 'receiving'), None)
            if receiving_data and receiving_data.get('athletes'):
                wr = receiving_data['athletes'][0]  # Top receiver
                wr_stats = wr.get('stats', [])
                if len(wr_stats) >= 4:
                    try:
                        yds = wr_stats[1]  # Receiving yards
                        tds = wr_stats[3]  # Receiving TDs
                        athlete_info = wr.get('athlete', {})
                        wr_name = self._abbreviate_name(
                            athlete_info.get('displayName', 'Unknown')
                        )
                        leaders['WR'] = {
                            'name': wr_name,
                            'stats': f"{yds} YDS, {tds} TD"
                        }
                    except (ValueError, IndexError):
                        pass

            # Extract RB (top rusher)
            rushing_data = next((s for s in stats_section if s.get('name') == 'rushing'), None)
            if rushing_data and rushing_data.get('athletes'):
                rb = rushing_data['athletes'][0]  # Top rusher
                rb_stats = rb.get('stats', [])
                if len(rb_stats) >= 4:
                    try:
                        yds = rb_stats[1]  # Rushing yards
                        tds = rb_stats[3]  # Rushing TDs
                        athlete_info = rb.get('athlete', {})
                        rb_name = self._abbreviate_name(
                            athlete_info.get('displayName', 'Unknown')
                        )
                        leaders['RB'] = {
                            'name': rb_name,
                            'stats': f"{yds} YDS, {tds} TD"
                        }
                    except (ValueError, IndexError):
                        pass

            return leaders if leaders else None

        except Exception as e:
            self.logger.debug(f"Error extracting football leaders: {e}")
            return None

    def _abbreviate_name(self, full_name: str) -> str:
        """
        Abbreviate player name for compact display.

        Args:
            full_name: Full player name (e.g., "Patrick Mahomes")

        Returns:
            Abbreviated name (e.g., "P. Mahomes" or "Mahomes")
        """
        parts = full_name.split()

        if len(parts) >= 2:
            # Use last name only if short enough
            if len(parts[-1]) <= 8:
                return parts[-1]
            # Otherwise use "F. Lastname" format
            return f"{parts[0][0]}. {parts[-1]}"

        # Single name or unknown - truncate if too long
        return full_name[:10] if len(full_name) > 10 else full_name
