from voxflow.scheduler import RecognitionScheduler


def test_partial_results_are_provisional_and_stop_forces_final_pass():
    scheduler = RecognitionScheduler(sample_rate=10, interval_seconds=1)
    scheduler.start()
    assert scheduler.next_job(sample_count=9) is None
    partial = scheduler.next_job(sample_count=10)
    assert partial.kind == "partial"
    scheduler.stop()
    assert scheduler.complete(partial, "hello") is None
    final = scheduler.next_job(sample_count=12)
    assert final.kind == "final"
    assert scheduler.complete(final, "hello world") == ("final", "hello world")
    assert scheduler.next_job(sample_count=12) is None


def test_old_session_result_cannot_replace_new_session_text():
    scheduler = RecognitionScheduler(sample_rate=10, interval_seconds=1)
    scheduler.start()
    old_job = scheduler.next_job(sample_count=10)
    scheduler.start()
    assert scheduler.complete(old_job, "stale") is None
    new_job = scheduler.next_job(sample_count=10)
    assert new_job.session_id != old_job.session_id
    assert scheduler.complete(new_job, "fresh") == ("partial", "fresh")
