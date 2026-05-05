"""
Execution Voter - Select the best SQL from multiple candidates using execution results.

Inspired by: CSC-SQL (Corrective Self-Consistency), CHASE-SQL (pairwise selection).

Voting logic:
1. Execute all candidates on the real DB
2. Group by execution result (same columns + same rows hash)
3. Select the group with the most candidates (majority vote)
4. Within the winning group → select candidate with lowest temperature (most precise)
5. If no candidate succeeds → return the first candidate for the correction loop to handle
"""

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy

from askdataai.generation.candidate_generator import Candidate, CandidateSet
from askdataai.generation.sql_rewriter import SQLRewriter

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Execution result for a single candidate."""
    candidate: Candidate
    success: bool
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    error: str = ""
    result_hash: str = ""  # Hash of result for comparison


@dataclass
class VotingResult:
    """Voting result."""
    best_candidate: Candidate
    best_sql_rewritten: str        # Rewritten SQL (DB names)
    execution_result: ExecutionResult | None
    total_candidates: int
    successful_candidates: int
    voting_method: str             # "majority", "single_success", "fallback"
    vote_distribution: dict[str, int] = field(default_factory=dict)


class ExecutionVoter:
    """
    Execution-based voting: select the best SQL from candidates.

    Execute → group by result → majority vote.
    """

    def __init__(
        self,
        engine: sqlalchemy.Engine,
        rewriter: SQLRewriter,
        row_limit: int = 50,
    ):
        self._engine = engine
        self._rewriter = rewriter
        self._row_limit = row_limit

    def vote(self, candidate_set: CandidateSet) -> VotingResult:
        """
        Vote to select the best SQL.

        Args:
            candidate_set: Candidate set from CandidateGenerator.

        Returns:
            VotingResult with the best candidate.
        """
        candidates = candidate_set.candidates
        if not candidates:
            raise ValueError("No candidates to vote on")

        # If only 1 candidate → skip voting
        if len(candidates) == 1:
            c = candidates[0]
            rewritten = self._rewriter.rewrite(c.sql)
            exec_result = self._execute(c, rewritten)
            return VotingResult(
                best_candidate=c,
                best_sql_rewritten=rewritten,
                execution_result=exec_result,
                total_candidates=1,
                successful_candidates=1 if exec_result.success else 0,
                voting_method="single",
            )

        # Execute all candidates
        exec_results: list[ExecutionResult] = []
        for c in candidates:
            rewritten = self._rewriter.rewrite(c.sql)
            result = self._execute(c, rewritten)
            exec_results.append(result)

        # Split into successful and failed
        successful = [r for r in exec_results if r.success]
        logger.info(
            f"Execution: {len(successful)}/{len(exec_results)} successful"
        )

        if not successful:
            # No candidates succeeded → fallback to first candidate
            logger.warning("No candidates executed successfully — using fallback")
            c = candidates[0]
            return VotingResult(
                best_candidate=c,
                best_sql_rewritten=self._rewriter.rewrite(c.sql),
                execution_result=exec_results[0],
                total_candidates=len(candidates),
                successful_candidates=0,
                voting_method="fallback",
            )

        if len(successful) == 1:
            # Only 1 candidate succeeded
            r = successful[0]
            return VotingResult(
                best_candidate=r.candidate,
                best_sql_rewritten=self._rewriter.rewrite(r.candidate.sql),
                execution_result=r,
                total_candidates=len(candidates),
                successful_candidates=1,
                voting_method="single_success",
            )

        # Majority vote by result hash
        return self._majority_vote(successful, len(candidates))

    def _majority_vote(
        self,
        successful: list[ExecutionResult],
        total: int,
    ) -> VotingResult:
        """Majority vote: group by result hash, select the largest group."""
        # Count votes by result hash
        hash_counter = Counter(r.result_hash for r in successful)
        vote_distribution = dict(hash_counter)

        # Find winning hash
        winning_hash = hash_counter.most_common(1)[0][0]
        winners = [r for r in successful if r.result_hash == winning_hash]

        # Among winners, select candidate with lowest temperature
        winners.sort(key=lambda r: r.candidate.temperature)
        best = winners[0]

        logger.info(
            f"Majority vote: {len(winners)}/{len(successful)} agree, "
            f"winning hash={winning_hash[:16]}..."
        )

        return VotingResult(
            best_candidate=best.candidate,
            best_sql_rewritten=self._rewriter.rewrite(best.candidate.sql),
            execution_result=best,
            total_candidates=total,
            successful_candidates=len(successful),
            voting_method="majority",
            vote_distribution=vote_distribution,
        )

    def _execute(
        self,
        candidate: Candidate,
        rewritten_sql: str,
    ) -> ExecutionResult:
        """Execute SQL on DB and hash the result."""
        try:
            with self._engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(rewritten_sql))
                columns = list(result.keys())
                rows = [
                    dict(zip(columns, row))
                    for row in result.fetchmany(self._row_limit)
                ]

                # Hash result for comparison
                result_hash = self._hash_result(columns, rows)

                return ExecutionResult(
                    candidate=candidate,
                    success=True,
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    result_hash=result_hash,
                )

        except Exception as e:
            error_msg = str(e)
            if "Original error" in error_msg:
                error_msg = error_msg.split("Original error")[0]

            logger.debug(
                f"Candidate [{candidate.strategy}] failed: {error_msg[:100]}"
            )
            return ExecutionResult(
                candidate=candidate,
                success=False,
                error=error_msg.strip(),
            )

    @staticmethod
    def _hash_result(columns: list[str], rows: list[dict]) -> str:
        """Hash execution result for comparison."""
        # Normalize: sort columns, convert values to string
        content = json.dumps(
            {"columns": sorted(columns), "rows": rows},
            sort_keys=True,
            default=str,
        )
        return hashlib.md5(content.encode()).hexdigest()
