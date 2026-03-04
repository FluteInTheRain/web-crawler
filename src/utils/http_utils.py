import certifi
import requests
from requests.adapters import HTTPAdapter


def make_http_session(
    user_agent: str = "Mozilla/5.0 (compatible; WebCrawler/1.0)",
) -> requests.Session:
    """
    Create a requests Session with SSL verification and a custom User-Agent.

    :param user_agent: Value for the User-Agent request header.
    :returns: Configured requests.Session instance.
    """
    session = requests.Session()
    adapter = HTTPAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = certifi.where()
    session.headers.update({"User-Agent": user_agent})
    return session
