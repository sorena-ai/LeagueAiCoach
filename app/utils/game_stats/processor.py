"""
Game state processor - High-level interface for processing game data into reports
"""

import json
import logging
from typing import Optional

from .models import MatchState
from .parser import GameParser
from .calculator import GameCalculator
from .report import ReportGenerator

logger = logging.getLogger(__name__)


class GameStateProcessor:
    """
    High-level processor for converting raw game JSON into formatted reports.

    This class encapsulates the full pipeline:
    1. Parse JSON -> MatchState
    2. Calculate stats from events
    3. Generate formatted report

    Use this class when you need a simple interface to process game data.
    """

    @staticmethod
    def process_to_report(game_stats_json: str) -> str:
        """
        Process raw game statistics JSON into a formatted text report.

        This is the main entry point for converting game data into a human-readable
        report. It handles the full pipeline: parsing, calculating, and formatting.

        Args:
            game_stats_json: Raw JSON string from League Client API

        Returns:
            Formatted text report with game state, objectives, teams, and battle log

        Raises:
            ValueError: If JSON is invalid or missing required fields
            Exception: If processing fails

        Example:
            >>> processor = GameStateProcessor()
            >>> report = processor.process_to_report(raw_json)
            >>> print(report)
        """
        try:
            # Parse JSON
            game_data = json.loads(game_stats_json)

            # Create parser and parse game state
            parser = GameParser(game_data)
            state = parser.parse()

            # Get events and calculate statistics
            events = game_data.get('events', {}).get('Events', [])
            calc = GameCalculator(state, events)
            calc.process()

            # Generate formatted report
            report = ReportGenerator.generate(state)

            logger.debug("Generated game stats report (%d characters)", len(report))

            return report

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in game_stats_json: %s", str(e))
            raise ValueError(f"Invalid JSON format: {str(e)}")
        except KeyError as e:
            logger.error("Missing required field in game data: %s", str(e))
            raise ValueError(f"Missing required field: {str(e)}")
        except Exception as e:
            logger.error("Failed to process game stats: %s", str(e))
            raise

    @staticmethod
    def process_to_state(game_stats_json: str) -> MatchState:
        """
        Process raw game statistics JSON into a MatchState object.

        Use this when you need programmatic access to game data rather than
        a formatted text report.

        Args:
            game_stats_json: Raw JSON string from League Client API

        Returns:
            MatchState object with all parsed and calculated data

        Raises:
            ValueError: If JSON is invalid or missing required fields
            Exception: If processing fails

        Example:
            >>> processor = GameStateProcessor()
            >>> state = processor.process_to_state(raw_json)
            >>> print(f"Dragons: {state.allies.dragons.count}")
        """
        try:
            # Parse JSON
            game_data = json.loads(game_stats_json)

            # Create parser and parse game state
            parser = GameParser(game_data)
            state = parser.parse()

            # Get events and calculate statistics
            events = game_data.get('events', {}).get('Events', [])
            calc = GameCalculator(state, events)
            calc.process()

            return state

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in game_stats_json: %s", str(e))
            raise ValueError(f"Invalid JSON format: {str(e)}")
        except KeyError as e:
            logger.error("Missing required field in game data: %s", str(e))
            raise ValueError(f"Missing required field: {str(e)}")
        except Exception as e:
            logger.error("Failed to process game stats: %s", str(e))
            raise

