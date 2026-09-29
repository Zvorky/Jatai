import concurrent.futures

from jatai.core.delivery import Delivery


def test_concurrent_delivery(temp_dir):
    """Test concurrent delivery of files to same OUTBOX to validate atomic rename."""
    outbox = temp_dir / "OUTBOX"
    outbox.mkdir()
    
    # Create 500 different source files
    sources_dir = temp_dir / "sources"
    sources_dir.mkdir()
    
    sources = []
    for i in range(500):
        src = sources_dir / f"file_{i}.txt"
        src.write_text(f"content {i}")
        sources.append(src)
        
    def deliver_file(src):
        d = Delivery(src, outbox)
        return d.deliver()
        
    # Deliver concurrently
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(deliver_file, src): src for src in sources}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    # Verify all 500 files arrived safely
    assert len(results) == 500
    for r in results:
        assert r.exists()
        
    # Verify no .tmp files leaked
    tmp_files = list(outbox.glob("*.tmp"))
    assert len(tmp_files) == 0
