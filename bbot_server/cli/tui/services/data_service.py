"""Data service for BBOT Server TUI"""

import asyncio
import logging
from typing import Optional, List, Any

from bbot_server.errors import BBOTServerError, BBOTServerUnauthorizedError


log = logging.getLogger(__name__)


class DataService:
    def __init__(self, bbot_server):
        self.bbot_server = bbot_server
        if hasattr(bbot_server, "_instance"):
            self._async_client = bbot_server._instance
            log.debug("Using native async client via ._instance")
        else:
            self._async_client = bbot_server
            log.warning("._instance not found, using sync wrapper as fallback")

    async def _fetch_paginated(
        self, query_method: str, count_method: str, skip: int = 0, limit: int = 25, **filters
    ) -> tuple[List[Any], int]:
        kwargs = {k: v for k, v in filters.items() if v is not None}
        try:
            query_fn = getattr(self._async_client, query_method)
            items = [item async for item in query_fn(skip=skip, limit=limit, **kwargs)]
            count_fn = getattr(self._async_client, count_method)
            total = await count_fn(**kwargs)
            log.debug(f"Fetched {len(items)} items (skip={skip}, limit={limit}, total={total})")
            return items, total
        except BBOTServerUnauthorizedError:
            raise
        except BBOTServerError:
            log.exception(f"Error in {query_method}")
            return [], 0
        except Exception:
            log.exception(f"Unexpected error in {query_method}")
            return [], 0

    async def get_scans(self) -> List[Any]:
        try:
            scans = [scan async for scan in self._async_client.get_scans()]
            log.debug(f"Fetched {len(scans)} scans")
            return scans
        except BBOTServerUnauthorizedError:
            raise
        except BBOTServerError:
            log.exception("Error fetching scans")
            return []

    async def get_scan_options(self):
        """Return current target and preset choices for the start dialog."""
        return await self._async_client.get_targets(), await self._async_client.get_presets()

    async def start_scan(self, **options):
        return await self._async_client.start_scan(**options)

    async def cancel_scan(self, scan_id):
        return await self._async_client.cancel_scan(id=scan_id)

    async def delete_scan(self, scan_id):
        return await self._async_client.delete_scan(id=scan_id)

    async def export_scan_report(self, scan, format="html"):
        from bbot_server.reporting import collect_report, report_path, write_report

        snapshot = await collect_report(self._async_client, scan=scan)
        return write_report(snapshot, format, report_path(scan).with_suffix(f".{format}"))

    async def get_targets(self):
        return await self._async_client.get_targets()

    async def get_scope_report(self, **scope):
        from bbot_server.reporting import collect_report

        return await collect_report(self._async_client, **scope)

    async def get_presets(self):
        return await self._async_client.get_presets()

    async def get_modules(self) -> List[dict[str, Any]]:
        """Return module metadata from the installed BBOT runtime."""
        return await asyncio.to_thread(self._get_modules)

    @staticmethod
    def _get_modules() -> List[dict[str, Any]]:
        from bbot.core.modules import MODULE_LOADER

        preloaded = MODULE_LOADER.preloaded()
        module_options = MODULE_LOADER.modules_options()
        modules = []
        for name, data in sorted(preloaded.items()):
            meta = data.get("meta", {})
            options = [
                {"name": option_name, "type": option_type, "description": description, "default": default}
                for option_name, option_type, description, default in module_options.get(name, [])
            ]
            modules.append(
                {
                    "name": name,
                    "type": data.get("type", "scan"),
                    "needs_api_key": bool(data.get("options_mandatory")),
                    "description": meta.get("description", ""),
                    "author": meta.get("author", ""),
                    "created_date": meta.get("created_date", ""),
                    "flags": sorted(data.get("flags", [])),
                    "watched_events": sorted(data.get("watched_events", [])),
                    "produced_events": sorted(data.get("produced_events", [])),
                    "options": options,
                }
            )
        return modules

    async def create_preset(self, preset):
        return await self._async_client.create_preset(preset=preset)

    async def update_preset(self, preset_id, preset):
        return await self._async_client.update_preset(preset_id=preset_id, preset=preset)

    async def delete_preset(self, preset_id):
        return await self._async_client.delete_preset(preset_id=preset_id)

    async def get_agents(self):
        return await self._async_client.get_agents()

    async def create_agent(self, name, description):
        return await self._async_client.create_agent(name=name, description=description)

    async def delete_agent(self, agent_id):
        return await self._async_client.delete_agent(id=agent_id)

    async def get_assets_paginated(self, skip: int = 0, limit: int = 25, **filters) -> tuple[List[Any], int]:
        return await self._fetch_paginated("query_assets", "count_assets", skip, limit, **filters)

    async def get_findings_paginated(self, skip: int = 0, limit: int = 25, **filters) -> tuple[List[Any], int]:
        return await self._fetch_paginated("query_findings", "count_findings", skip, limit, **filters)

    async def get_events_paginated(self, skip: int = 0, limit: int = 25, **filters) -> tuple[List[Any], int]:
        return await self._fetch_paginated("query_events", "count_events", skip, limit, **filters)

    async def get_scans_paginated(self, skip: int = 0, limit: int = 25, **filters) -> tuple[List[Any], int]:
        return await self._fetch_paginated("query_scans", "count_scans", skip, limit, **filters)

    async def get_technologies_paginated(self, skip: int = 0, limit: int = 25, **filters) -> tuple[List[Any], int]:
        return await self._fetch_paginated("query_technologies", "count_technologies", skip, limit, **filters)

    async def get_targets_paginated(self, skip: int = 0, limit: int = 25, **filters) -> tuple[List[Any], int]:
        return await self._fetch_paginated("query_targets", "count_targets", skip, limit, **filters)

    async def create_target(
        self,
        name: str,
        description: str = "",
        target: Optional[List[str]] = None,
        seeds: Optional[List[str]] = None,
        blacklist: Optional[List[str]] = None,
        strict_scope: bool = False,
    ) -> Optional[Any]:
        try:
            target_data = {
                "name": name,
                "description": description,
                "target": target or [],
                "blacklist": blacklist or [],
                "strict_scope": strict_scope,
            }
            if seeds is not None:
                target_data["seeds"] = seeds
            log.info(f"Creating target: {name}")
            created_target = await self._async_client.create_target(**target_data)
            log.info(f"Created target: {name}")
            return created_target
        except BBOTServerError:
            log.exception("Error creating target")
            raise

    async def update_target(
        self,
        target_id: str,
        name: str,
        description: str = "",
        target: Optional[List[str]] = None,
        seeds: Optional[List[str]] = None,
        blacklist: Optional[List[str]] = None,
        strict_scope: bool = False,
    ) -> Optional[Any]:
        try:
            from bbot_server.modules.targets.targets_models import Target as TargetModel

            target_data = {
                "name": name,
                "description": description,
                "target": target or [],
                "blacklist": blacklist or [],
                "strict_scope": strict_scope,
            }
            if seeds is not None:
                target_data["seeds"] = seeds
            log.info(f"Updating target {target_id}: {name}")
            target_model = TargetModel(**target_data)
            updated_target = await self._async_client.update_target(id=target_id, target=target_model)
            log.info(f"Updated target: {name}")
            return updated_target
        except BBOTServerError:
            log.exception("Error updating target")
            raise

    async def delete_target(self, target_id: str) -> None:
        try:
            log.info(f"Deleting target {target_id}")
            await self._async_client.delete_target(id=target_id)
            log.info(f"Deleted target: {target_id}")
        except BBOTServerError:
            log.exception("Error deleting target")
            raise
