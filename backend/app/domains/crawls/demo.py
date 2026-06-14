from uuid import uuid4


class DemoCrawlerProvider:
    def start(self, url: str, *, limit: int, metadata: dict) -> dict:
        root = url.rstrip("/")
        documents = [
            {
                "markdown": "# SHM Transmissie\nSpecialist in transmissies.",
                "links": [f"{root}/revisie", f"{root}/contact", f"{root}/kapot"],
                "metadata": {
                    "sourceURL": root,
                    "statusCode": 200,
                    "title": "SHM Transmissie",
                    "description": "Transmissiespecialist",
                    "canonicalUrl": root,
                },
            },
            {
                "markdown": "# Transmissie revisie\nVakmanschap en diagnose.",
                "links": [root, f"{root}/contact"],
                "metadata": {
                    "sourceURL": f"{root}/revisie",
                    "statusCode": 200,
                    "title": "Transmissie revisie",
                    "description": "Transmissie revisie",
                    "canonicalUrl": f"{root}/revisie",
                },
            },
            {
                "markdown": "# Contact",
                "links": [root],
                "metadata": {
                    "sourceURL": f"{root}/contact",
                    "statusCode": 200,
                    "title": "",
                    "description": "Neem contact op",
                    "canonicalUrl": f"{root}/contact",
                },
            },
            {
                "markdown": "# Niet gevonden",
                "links": [],
                "metadata": {
                    "sourceURL": f"{root}/kapot",
                    "statusCode": 404,
                    "title": "Niet gevonden",
                },
            },
        ]
        return {"id": f"demo-{uuid4()}", "data": documents[:limit]}

    def status(self, crawl_id: str) -> dict:
        return {"id": crawl_id, "status": "completed"}

    def cancel(self, crawl_id: str) -> None:
        return None

    def verify_webhook(self, body: bytes, signature: str | None) -> bool:
        return False
