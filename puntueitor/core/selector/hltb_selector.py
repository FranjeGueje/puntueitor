from howlongtobeatpy import HowLongToBeatEntry


class HLTBSelector():
    @staticmethod
    def select(results: list[HowLongToBeatEntry]) -> HowLongToBeatEntry | None:
        if not results:
            return None

        # heurística básica: el primero suele ser el mejor
        return results[0]
