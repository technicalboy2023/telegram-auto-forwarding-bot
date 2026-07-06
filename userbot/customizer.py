"""
Post Customization Engine for the Telegram Auto-Forwarding Bot.

Processing pipeline (order matters):
    Raw Post → Block Check → Word Replacements → Add Header → Add Footer → Done

Features:
- Word/Phrase Replacement — any word to any word
- Word Blocking — skip posts containing blocked words
- Header/Footer — prepend/append text
- Empty line cleanup
- Caption handling for media posts
"""

import re
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class PostCustomizer:
    """
    Processes incoming posts through a configurable pipeline.

    Each post goes through:
    1. Block check — if a blocked word is found, post is rejected
    2. Word replacement — all replace rules are applied sequentially
    3. Header addition — header text is prepended
    4. Footer addition — footer text is appended
    5. Whitespace cleanup — excessive blank lines trimmed
    """

    def __init__(
        self,
        replace_rules: Optional[list[dict]] = None,
        block_words: Optional[list[str]] = None,
        header: str = "",
        footer: str = "",
    ):
        """
        Args:
            replace_rules: List of {"old_word": str, "new_word": str} dicts
            block_words: List of words/phrases that cause rejection
            header: Text to prepend to every forwarded post
            footer: Text to append to every forwarded post
        """
        self.replace_rules = replace_rules or []
        self.block_words = block_words or []
        self.header = header
        self.footer = footer

    # ── Public API ────────────────────────────────────────

    def update_config(
        self,
        replace_rules: list[dict],
        block_words: list[str],
        header: str,
        footer: str,
    ) -> None:
        """Reload all customization configuration from the database."""
        self.replace_rules = replace_rules
        self.block_words = block_words
        self.header = header
        self.footer = footer
        logger.debug(
            "Config reloaded: %d replaces, %d blocks, header=%d chars, footer=%d chars",
            len(self.replace_rules),
            len(self.block_words),
            len(self.header),
            len(self.footer),
        )

    def should_block(self, text: str) -> tuple[bool, Optional[str]]:
        """
        Check if text contains any blocked word.

        Returns:
            (blocked, word_found) — True and the matched word if blocked,
            False and None otherwise.
        """
        if not text or not self.block_words:
            return False, None

        text_lower = text.lower()
        for word in self.block_words:
            if word.lower() in text_lower:
                logger.info("Post blocked — contains word: '%s'", word)
                return True, word
        return False, None

    def apply_replacements(self, text: str) -> str:
        """
        Apply all replace rules to the text, in order.
        Case-insensitive matching (consistent with should_block).
        Returns the modified text.
        """
        if not text or not self.replace_rules:
            return text

        for rule in self.replace_rules:
            old = rule.get("old_word", "")
            new = rule.get("new_word", "")
            if not old:
                continue
            # Case-insensitive replace using regex
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            text = pattern.sub(new, text)
            logger.debug("Replaced '%s' -> '%s'", old, new)

        return text

    def apply_header(self, text: str) -> str:
        """Prepend header text if configured."""
        if not self.header:
            return text
        return f"{self.header}\n{text}"

    def apply_footer(self, text: str) -> str:
        """Append footer text if configured."""
        if not self.footer:
            return text
        return f"{text}\n{self.footer}"

    def clean_whitespace(self, text: str) -> str:
        """Remove excessive blank lines (≥ 3 consecutive newlines → 2)."""
        if not text:
            return text
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def process(self, text: str) -> Optional[str]:
        """
        Run the full customization pipeline.

        Returns:
            Customized text string, or None if the post should be blocked.
        """
        if not text:
            return None

        # 1. Block check
        blocked, word = self.should_block(text)
        if blocked:
            logger.info("Post rejected — blocked word '%s' found.", word)
            return None

        # 2. Word replacements
        text = self.apply_replacements(text)

        # 3. Header
        text = self.apply_header(text)

        # 4. Footer
        text = self.apply_footer(text)

        # 5. Whitespace cleanup
        text = self.clean_whitespace(text)

        return text

    def process_caption(self, caption: Optional[str]) -> Optional[str]:
        """
        Process a media caption through the same pipeline.
        Same as process() but handles None gracefully.
        """
        if caption is None:
            return None
        return self.process(caption)
