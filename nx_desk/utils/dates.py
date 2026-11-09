from datetime import datetime
from typing import Optional


# A time with its zone, or None when the text is not one.
def parse_time(value: object) -> Optional[datetime]:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    except ValueError:
        return None

    return moment if moment.tzinfo else None
