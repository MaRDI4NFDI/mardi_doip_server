from doip_shared.sharding import shard_qid, get_component_path


def test_shard_qid_examples():
    assert shard_qid("Q4") == "00/00/04/Q4"
    assert shard_qid("Q123") == "00/01/23/Q123"
    assert shard_qid("Q12345") == "01/23/45/Q12345"
    assert shard_qid("Q123543") == "12/35/43/Q123543"


def test_get_component_path_uses_sharded_prefix():
    path = get_component_path("Q123", "primary", "pdf")
    assert path == "00/01/23/Q123/components/primary.pdf"
