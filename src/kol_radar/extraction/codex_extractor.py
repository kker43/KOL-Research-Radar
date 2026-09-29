from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Protocol

from pydantic import ValidationError

from kol_radar.domain import OpinionDraft
from kol_radar.extraction.base import OpinionExtractionError
from kol_radar.extraction.prompts import SYSTEM_PROMPT, format_article
from kol_radar.extraction.validation import (
    OpinionExtractionResult,
    strict_opinion_json_schema,
    validate_opinion_evidence,
)
from kol_radar.providers.base import FetchedArticle


logger = logging.getLogger(__name__)


class CodexRunner(Protocol):
    def generate(self, *, prompt: str, schema: dict[str, object]) -> str: ...


class CodexCLIRunner:
    def __init__(
        self,
        *,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout_seconds: int = 300,
    ):
        self.command_runner = command_runner
        self.timeout_seconds = timeout_seconds
        self._executable_path: str | None = None

    @staticmethod
    def _environment() -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("OPENAI_API_KEY", None)
        return environment

    def _ensure_chatgpt_login(self) -> str:
        if self._executable_path is not None:
            return self._executable_path
        executable_path = shutil.which("codex")
        if executable_path is None:
            raise OpinionExtractionError(
                "Codex CLI is not installed. Install Codex, then run 'codex login'."
            )
        try:
            status = self.command_runner(
                [executable_path, "login", "status"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                env=self._environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise OpinionExtractionError(
                "Could not check Codex authentication. Run 'codex login' and try again."
            ) from error
        status_text = f"{status.stdout}\n{status.stderr}".casefold()
        if status.returncode != 0 or "chatgpt" not in status_text:
            raise OpinionExtractionError(
                "Codex is not authenticated with ChatGPT. Run 'codex login' and choose "
                "ChatGPT sign-in."
            )
        self._executable_path = executable_path
        return executable_path

    def generate(self, *, prompt: str, schema: dict[str, object]) -> str:
        executable_path = self._ensure_chatgpt_login()
        with tempfile.TemporaryDirectory(prefix="kol-radar-codex-") as directory:
            schema_path = Path(directory) / "opinion-output-schema.json"
            schema_path.write_text(
                json.dumps(schema, ensure_ascii=False), encoding="utf-8"
            )
            command = [
                executable_path,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--output-schema",
                str(schema_path),
                "--color",
                "never",
                "-",
            ]
            try:
                result = self.command_runner(
                    command,
                    input=prompt,
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.timeout_seconds,
                    env=self._environment(),
                )
            except subprocess.TimeoutExpired as error:
                raise OpinionExtractionError("Codex extraction timed out.") from error
            except OSError as error:
                raise OpinionExtractionError(
                    "Codex extraction process could not start."
                ) from error
            if result.returncode != 0:
                raise OpinionExtractionError(
                    f"Codex extraction failed with exit code {result.returncode}."
                )
            return result.stdout.strip()


class CodexOpinionExtractor:
    def __init__(self, runner: CodexRunner | None = None):
        self.runner = runner or CodexCLIRunner()
        self.last_rejected_count = 0

    def extract(self, article: FetchedArticle) -> list[OpinionDraft]:
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            "Return only JSON matching the supplied output schema.\n\n"
            f"{format_article(article)}"
        )
        output = self.runner.generate(
            prompt=prompt, schema=strict_opinion_json_schema()
        )
        try:
            result = OpinionExtractionResult.model_validate(json.loads(output))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            self.last_rejected_count = 0
            raise OpinionExtractionError(
                "Codex returned invalid structured JSON."
            ) from error

        accepted, self.last_rejected_count = validate_opinion_evidence(
            article, result.opinions
        )
        if self.last_rejected_count:
            logger.info("opinions_rejected count=%s", self.last_rejected_count)
        return accepted
