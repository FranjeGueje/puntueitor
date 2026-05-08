from howlongtobeatpy import HowLongToBeat, SearchModifiers
from puntueitor.core.raw.howlongtobeat.hltb_entry import HLTBEntry
from puntueitor.core.enrichers.hltb_enricher import HLTBClient

class HLTBResolver(HLTBClient):
    def __init__(
        self,
        *,
        hide_dlc: bool = True,
        limit: int = 5,
    ) -> None:
        self._client = HowLongToBeat()
        self.hide_dlc = hide_dlc
        self.limit = limit
    
    def search(self, title: str) -> HLTBEntry | None:
        if not title.strip():
            return None

        if self.hide_dlc:
            results = self._client.search(
                game_name=title,
                search_modifiers=SearchModifiers.HIDE_DLC,
            )
        else:
            results = self._client.search(
                game_name=title,
            )

        if not results:
            return None

        best = results[0]

        return HLTBEntry(
            hltb_id=best.game_id,
            name=best.game_name,
            similarity=best.similarity,
            main_story=best.main_story,
            main_extra=best.main_extra,
            completionist=best.completionist,
            url=best.game_web_link,
        )
