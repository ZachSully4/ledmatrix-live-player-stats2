"""
Rendering module for LivePlayerStats plugin.

Handles PIL-based rendering of player stat cards for scrolling display.
"""

from typing import Dict, Optional
from PIL import Image, ImageDraw, ImageFont


# Color scheme
COLOR_WHITE = (255, 255, 255)
COLOR_LIGHT_BLUE = (77, 190, 238)
COLOR_GRAY = (170, 170, 170)
COLOR_BLACK = (0, 0, 0)


class StatsRenderer:
    """Renders player statistics as game cards for scrolling display."""

    def __init__(self, font_manager, logger, display_height=32):
        """
        Initialize stats renderer.

        Args:
            font_manager: FontManager instance for font access
            logger: Logger instance
            display_height: Display height in pixels (default: 32)
        """
        self.font_manager = font_manager
        self.logger = logger
        self.display_height = display_height

        # Load fonts (using compact fonts for small display)
        import os
        try:
            # Try to get 4x6 font for compact display
            self.small_font = ImageFont.load_default()
            self.medium_font = ImageFont.load_default()

            # Attempt to load better fonts if available
            # Try to find the LEDMatrix root directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            ledmatrix_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
            font_dir = os.path.join(ledmatrix_root, 'assets', 'fonts')

            try:
                font_path_4x6 = os.path.join(font_dir, '4x6-font.ttf')
                if os.path.exists(font_path_4x6):
                    self.small_font = ImageFont.truetype(font_path_4x6, 6)
                    self.medium_font = ImageFont.truetype(font_path_4x6, 8)
            except Exception as e:
                self.logger.debug(f"Could not load custom fonts: {e}")
                pass

        except Exception as e:
            self.logger.warning(f"Error loading fonts, using defaults: {e}")
            self.small_font = ImageFont.load_default()
            self.medium_font = ImageFont.load_default()

    def render_game_card(self, game_data: Dict, card_width: int = 100) -> Image.Image:
        """
        Render a game card with player statistics.

        Args:
            game_data: Game dictionary with team info and stat leaders
            card_width: Width of the card in pixels (default: 100)

        Returns:
            PIL Image of the game card
        """
        # Create image
        img = Image.new('RGB', (card_width, self.display_height), color=COLOR_BLACK)
        draw = ImageDraw.Draw(img)

        try:
            # Extract game info
            away_abbr = game_data.get('away_abbr', 'AWAY')
            home_abbr = game_data.get('home_abbr', 'HOME')
            away_score = game_data.get('away_score', 0)
            home_score = game_data.get('home_score', 0)
            period_text = game_data.get('period_text', '')
            clock = game_data.get('clock', '')
            away_leaders = game_data.get('away_leaders')
            home_leaders = game_data.get('home_leaders')

            # Vertical layout positions
            y_pos = 1

            # Draw game header (matchup and status)
            header = f"{away_abbr} {away_score} @ {home_abbr} {home_score}"
            draw.text((2, y_pos), header, font=self.small_font, fill=COLOR_WHITE)
            y_pos += 7

            # Draw game status (period/clock)
            if period_text:
                status_text = period_text[:15]  # Truncate if too long
                draw.text((2, y_pos), status_text, font=self.small_font, fill=COLOR_GRAY)
                y_pos += 7

            # Draw away team leaders (one line per stat category)
            if away_leaders:
                leader_lines = self._format_leaders_detailed(away_abbr, away_leaders)
                for line in leader_lines:
                    draw.text((2, y_pos), line, font=self.small_font, fill=COLOR_LIGHT_BLUE)
                    y_pos += 6
            else:
                # No stats available yet
                draw.text((2, y_pos), f"{away_abbr}: N/A", font=self.small_font, fill=COLOR_GRAY)
                y_pos += 6

            # Draw home team leaders (one line per stat category)
            if home_leaders:
                leader_lines = self._format_leaders_detailed(home_abbr, home_leaders)
                for line in leader_lines:
                    draw.text((2, y_pos), line, font=self.small_font, fill=COLOR_LIGHT_BLUE)
                    y_pos += 6
            else:
                # No stats available yet
                draw.text((2, y_pos), f"{home_abbr}: N/A", font=self.small_font, fill=COLOR_GRAY)
                y_pos += 6

            return img

        except Exception as e:
            self.logger.error(f"Error rendering game card: {e}", exc_info=True)
            # Return error card
            return self._create_error_card(card_width)

    def _format_leaders_detailed(self, team_abbr: str, leaders: Dict) -> list:
        """
        Format leader stats with one line per stat category.

        Args:
            team_abbr: Team abbreviation
            leaders: Dictionary of stat leaders

        Returns:
            List of formatted strings, one per stat leader
        """
        if not leaders:
            return []

        lines = []

        # Check if this is basketball or football stats
        if 'PTS' in leaders or 'REB' in leaders or 'AST' in leaders:
            # Basketball format: Show each leader separately
            if 'PTS' in leaders:
                pts_leader = leaders['PTS']
                name = self._abbreviate_display_name(pts_leader.get('name', '?'), max_length=10)
                value = pts_leader.get('value', 0)
                lines.append(f"{team_abbr} PTS: {name} {value}")

            if 'REB' in leaders:
                reb_leader = leaders['REB']
                name = self._abbreviate_display_name(reb_leader.get('name', '?'), max_length=10)
                value = reb_leader.get('value', 0)
                lines.append(f"{team_abbr} REB: {name} {value}")

            if 'AST' in leaders:
                ast_leader = leaders['AST']
                name = self._abbreviate_display_name(ast_leader.get('name', '?'), max_length=10)
                value = ast_leader.get('value', 0)
                lines.append(f"{team_abbr} AST: {name} {value}")

        elif 'QB' in leaders or 'WR' in leaders or 'RB' in leaders:
            # Football format: Show each position leader
            if 'QB' in leaders:
                name = leaders['QB'].get('name', '?')
                stats = leaders['QB'].get('stats', '')
                stats_short = stats.replace(' YDS', '').replace(' TD', 'TD')
                lines.append(f"{team_abbr} QB: {name} {stats_short}")

            if 'WR' in leaders:
                name = leaders['WR'].get('name', '?')
                stats = leaders['WR'].get('stats', '')
                stats_short = stats.replace(' YDS', '').replace(' TD', 'TD')
                lines.append(f"{team_abbr} WR: {name} {stats_short}")

            if 'RB' in leaders:
                name = leaders['RB'].get('name', '?')
                stats = leaders['RB'].get('stats', '')
                stats_short = stats.replace(' YDS', '').replace(' TD', 'TD')
                lines.append(f"{team_abbr} RB: {name} {stats_short}")

        return lines

    def _format_leaders(self, team_abbr: str, leaders: Dict) -> str:
        """
        Format leader stats as a compact string (legacy method).

        Args:
            team_abbr: Team abbreviation
            leaders: Dictionary of stat leaders

        Returns:
            Formatted string (e.g., "LAL: LBJ 24/8/7" or "KC: Mahomes 245 YDS")
        """
        if not leaders:
            return ""

        # Check if this is basketball or football stats
        if 'PTS' in leaders:
            # Basketball format: "Team: Name PTS/REB/AST"
            pts = leaders.get('PTS', {}).get('value', 0)
            reb = leaders.get('REB', {}).get('value', 0)
            ast = leaders.get('AST', {}).get('value', 0)
            name = leaders.get('PTS', {}).get('name', 'Unknown')

            # Abbreviate name if too long
            name = self._abbreviate_display_name(name, max_length=8)

            return f"{team_abbr}: {name} {pts}/{reb}/{ast}"

        elif 'QB' in leaders or 'WR' in leaders or 'RB' in leaders:
            # Football format: Show top stat category
            # Priority: QB > WR > RB
            if 'QB' in leaders:
                name = leaders['QB'].get('name', 'Unknown')
                stats = leaders['QB'].get('stats', '')
                # Simplify stats for display
                stats_short = stats.replace(' YDS', '').replace(' TD', 'TD')
                return f"{team_abbr}: {name} {stats_short}"
            elif 'WR' in leaders:
                name = leaders['WR'].get('name', 'Unknown')
                stats = leaders['WR'].get('stats', '')
                stats_short = stats.replace(' YDS', '').replace(' TD', 'TD')
                return f"{team_abbr}: {name} {stats_short}"
            elif 'RB' in leaders:
                name = leaders['RB'].get('name', 'Unknown')
                stats = leaders['RB'].get('stats', '')
                stats_short = stats.replace(' YDS', '').replace(' TD', 'TD')
                return f"{team_abbr}: {name} {stats_short}"

        return ""

    def _abbreviate_display_name(self, name: str, max_length: int = 8) -> str:
        """
        Abbreviate name for display if too long.

        Args:
            name: Full name
            max_length: Maximum length

        Returns:
            Abbreviated name
        """
        if len(name) <= max_length:
            return name

        # Try splitting and using initials
        parts = name.split()
        if len(parts) >= 2:
            # Use initials: "LeBron James" -> "LJ"
            initials = ''.join([p[0] for p in parts[:2]])
            if len(initials) <= max_length:
                return initials

        # Truncate
        return name[:max_length]

    def _create_error_card(self, card_width: int) -> Image.Image:
        """
        Create an error card when rendering fails.

        Args:
            card_width: Width of the card

        Returns:
            PIL Image with error message
        """
        img = Image.new('RGB', (card_width, self.display_height), color=COLOR_BLACK)
        draw = ImageDraw.Draw(img)
        draw.text((2, 12), "Error", font=self.small_font, fill=COLOR_WHITE)
        return img

    def create_no_games_placeholder(self, width: int = 192) -> Image.Image:
        """
        Create a placeholder image when no live games are available.

        Args:
            width: Width of the placeholder image

        Returns:
            PIL Image with "No live games" message
        """
        img = Image.new('RGB', (width, self.display_height), color=COLOR_BLACK)
        draw = ImageDraw.Draw(img)

        message = "No live games"
        # Center the text
        try:
            # Try to get text dimensions for centering
            bbox = draw.textbbox((0, 0), message, font=self.medium_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except:
            # Fallback if textbbox not available
            text_width = len(message) * 6
            text_height = 8

        x = (width - text_width) // 2
        y = (self.display_height - text_height) // 2

        draw.text((x, y), message, font=self.medium_font, fill=COLOR_GRAY)
        return img
