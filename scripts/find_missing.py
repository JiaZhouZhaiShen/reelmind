import os, sys
sys.path.insert(0, '/app')
os.environ['DJANGO_SETTINGS_MODULE'] = ''

from app.database import sync_session_factory
from app.models.asset import Asset
from sqlalchemy import select

s = sync_session_factory()
with s:
    result = s.execute(select(Asset).where(Asset.thumbnail_path.isnot(None)))
    assets = result.scalars().all()
    missing = []
    ok_count = 0
    for a in assets:
        if a.thumbnail_path and not os.path.exists(a.thumbnail_path):
            missing.append(a)
        else:
            ok_count += 1
    print(f"Total assets with thumbnail_path: {len(assets)}")
    print(f"OK: {ok_count}")
    print(f"Missing: {len(missing)}")
    for a in missing:
        print(f"MISS: {a.file_name} | id={a.id} | path={a.original_path}")
