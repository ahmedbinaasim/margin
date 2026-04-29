# margin (Python SDK)

```bash
pip install margin
```

```python
from margin import Margin

m = Margin(api_key="ag_live_...")
project = m.start_research(topic="free-tier MCP hosting", depth="thorough")
finding = m.add_finding(
    project["project_id"],
    claim="Render free tier sleeps after 15 minutes",
    evidence="Render docs: 'Free web services spin down after 15 minutes ...'",
    source="https://render.com/docs/free",
    confidence=0.9,
)
m.cite(finding["finding_id"], url="https://render.com/docs/free", excerpt="...")
hits = m.query_findings(project["project_id"], semantic_query="cold start times")
report = m.publish_report(project["project_id"])
print(report["report_url"])
```

## Async

```python
from margin import AsyncMargin

async def main():
    async with AsyncMargin(api_key="ag_live_...") as m:
        p = await m.start_research(topic="...", depth="standard")
```

MIT licensed.
