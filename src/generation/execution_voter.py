"""
Execution Voter - Chọn SQL tốt nhất từ nhiều candidates bằng execution results.

Inspired by: CSC-SQL (Corrective Self-Consistency), CHASE-SQL (pairwise selection).

Logic voting:
1. Execute tất cả candidates trên DB thật
2. Nhóm theo execution result (cùng columns + cùng rows hash)
3. Chọn nhóm có nhiều candidates nhất (majority vote)
4. Trong nhóm chiến thắng → chọn candidate có temperature thấp nhất (most precise)
5. Nếu không candidate nào chạy được → trả về candidate đầu tiên để correction loop xử lý
"""

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy

from src.generation.candidate_generator import Candidate, CandidateSet
from src.generation.sql_rewriter import SQLRewriter

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Kết quả execute 1 candidate."""
    candidate: Candidate
    success: bool
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    error: str = ""
    result_hash: str = ""  # Hash của kết quả để so sánh


@dataclass
class VotingResult:
    """Kết quả voting."""
    best_candidate: Candidate
    best_sql_rewritten: str        # SQL đã rewrite (DB names)
    execution_result: ExecutionResult | None
    total_candidates: int
    successful_candidates: int
    voting_method: str             # "majority", "single_success", "fallback"
    vote_distribution: dict[str, int] = field(default_factory=dict)


class ExecutionVoter:
    """
    Execution-based voting: chọn SQL tốt nhất từ candidates.

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
        Vote chọn SQL tốt nhất.

        Args:
            candidate_set: Tập candidates từ CandidateGenerator.

        Returns:
            VotingResult với best candidate.
        """
        candidates = candidate_set.candidates
        if not candidates:
            raise ValueError("No candidates to vote on")

        # Nếu chỉ có 1 candidate → skip voting
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

        # Execute tất cả candidates
        exec_results: list[ExecutionResult] = []
        for c in candidates:
            rewritten = self._rewriter.rewrite(c.sql)
            result = self._execute(c, rewritten)
            exec_results.append(result)

        # Tách thành successful và failed
        successful = [r for r in exec_results if r.success]
        logger.info(
            f"Execution: {len(successful)}/{len(exec_results)} successful"
        )

        if not successful:
            # Không candidate nào chạy được → fallback candidate đầu tiên
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
            # Chỉ 1 candidate thành công
            r = successful[0]
            return VotingResult(
                best_candidate=r.candidate,
                best_sql_rewritten=self._rewriter.rewrite(r.candidate.sql),
                execution_result=r,
                total_candidates=len(candidates),
                successful_candidates=1,
                voting_method="single_success",
            )

        # Majority vote bằng result hash
        return self._majority_vote(successful, len(candidates))

    def _majority_vote(
        self,
        successful: list[ExecutionResult],
        total: int,
    ) -> VotingResult:
        """Majority vote: nhóm theo result hash, chọn nhóm lớn nhất."""
        # Count votes theo result hash
        hash_counter = Counter(r.result_hash for r in successful)
        vote_distribution = dict(hash_counter)

        # Tìm hash chiến thắng
        winning_hash = hash_counter.most_common(1)[0][0]
        winners = [r for r in successful if r.result_hash == winning_hash]

        # Trong winners, chọn candidate có temperature thấp nhất
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
        """Execute SQL trên DB, hash kết quả."""
        try:
            with self._engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(rewritten_sql))
                columns = list(result.keys())
                rows = [
                    dict(zip(columns, row))
                    for row in result.fetchmany(self._row_limit)
                ]

                # Hash kết quả để so sánh
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
        """Hash execution result để so sánh."""
        # Normalize: sort columns, convert values to string
        content = json.dumps(
            {"columns": sorted(columns), "rows": rows},
            sort_keys=True,
            default=str,
        )
        return hashlib.md5(content.encode()).hexdigest()
