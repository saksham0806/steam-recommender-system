import httpx
import re
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


async def scrape_tags_from_store(app_id: int) -> Optional[List[str]]:
    """
    Scrape popular tags from Steam store page
    """
    url = f"https://store.steampowered.com/app/{app_id}"
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(url)
            
            if response.status_code != 200:
                return None
            
            html = response.text
            
            # Find tags in the HTML
            # Tags are in: <a class="app_tag" ...>TagName</a>
            tag_pattern = r'<a[^>]*class="app_tag"[^>]*>([^<]+)</a>'
            matches = re.findall(tag_pattern, html)
            
            if matches:
                # Clean and limit to top 10 tags
                tags = [tag.strip() for tag in matches[:10]]
                logger.debug(f"Found {len(tags)} tags for app {app_id}")
                return tags
            
            return None
            
    except Exception as e:
        logger.debug(f"Failed to scrape tags for app {app_id}: {e}")
        return None