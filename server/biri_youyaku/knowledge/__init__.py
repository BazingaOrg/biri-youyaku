"""Knowledge registry + FTS summary/transcript search / opt-in chat / lifecycle.

Public surface:
- try_register_job / register_from_job
- reconcile_once
- unlink_job / unlink_jobs (via repo)
- lifecycle soft_delete / restore / purge_permanent
- backup create_backup
- index / search / retrieve / chat modules (imported by routes)
"""

from biri_youyaku.knowledge.reconcile import reconcile_once
from biri_youyaku.knowledge.register import register_from_job, try_register_job
from biri_youyaku.knowledge.repo import unlink_job, unlink_jobs

__all__ = [
    "reconcile_once",
    "register_from_job",
    "try_register_job",
    "unlink_job",
    "unlink_jobs",
]
