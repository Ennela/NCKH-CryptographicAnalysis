"""
shared.db.repositories — Repository pattern cho các bảng hypertable.

Các bảng khối lượng lớn (market.ohlcv_raw, market.ohlcv, ops.job_log, …)
KHÔNG có ORM model — truy cập bằng ``sqlalchemy.text()`` qua repository.
"""
