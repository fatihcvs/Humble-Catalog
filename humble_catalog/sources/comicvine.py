import os
from datetime import datetime, timedelta, timezone
from humble_catalog import outbound
from humble_catalog.sources.base import Source, candidate

class ComicVine(Source):
    name = "comicvine"
    delay = 20.0  # stays under Comic Vine's 200 requests/hour
    secret_params = ("api_key",)
    # The only hosts a Comic Vine URL taken from a Comic Vine response may
    # name. Every request to them carries the API key, so this is an
    # allowlist and not a routability check.
    API_HOSTS = frozenset({"comicvine.gamespot.com", "www.comicvine.com"})

    def __init__(self, conn, http=None, key=None, offline=False):
        super().__init__(conn, http=http, offline=offline)
        self.key = key if key is not None else os.environ.get("COMICVINE_API_KEY")

    def quota_resets_at(self, now=None):
        # 200 requests per resource, per hour - so the hour is Comic Vine's
        # own documented window, not the base class's fallback that happens
        # to match it. Declared so a later change to that fallback cannot
        # silently move it.
        #
        # This is the source most likely to hit its limit in normal use:
        # delay=20.0 puts a run at 180/hr against a 200/hr cap. The limit
        # being per *resource* means search/ and issue/ have separate
        # budgets, so the --credits top-up does not spend the search one.
        return (now or datetime.now(timezone.utc)) + timedelta(hours=1)

    def lookup(self, title):
        if not self.key:
            return []
        data = self.get_json(
            "https://comicvine.gamespot.com/api/search/",
            params={"api_key": self.key, "format": "json",
                    "resources": "volume", "query": title, "limit": 5})
        out = []
        for vol in data.get("results", []):
            out.append(candidate(
                source=self.name, title=vol.get("name", ""),
                series=vol.get("name"),
                url=vol.get("site_detail_url"),
                extra={"volume_api_url": vol.get("api_detail_url"),
                       # roles live on issues, so keep the first issue's URL
                       # from this response rather than re-fetching it later
                       "first_issue_api_url":
                           (vol.get("first_issue") or {}).get("api_detail_url")}))
        return out

    def credits(self, issue_api_url):
        """Writers and artists for one issue, as comma-joined strings.

        Must be an *issue* URL: `person_credits` is a field of the issue
        resource. Volumes only expose `people`, an unroled list of everyone
        who ever worked on the series, and asking a volume for
        `person_credits` returns error "OK" with an empty result.

        `issue_api_url` is not ours: it is `api_detail_url` copied out of a
        previous Comic Vine response, and this request carries the API key
        in its query string. So the host is checked against API_HOSTS
        before the request is sent - routability would not be enough, since
        an attacker's own server is routable and would be handed the key.
        Raises ValueError when the URL points anywhere else.
        """
        if not self.key or not issue_api_url:
            return None, None
        outbound.check_url(issue_api_url, allowed_hosts=self.API_HOSTS,
                           what="a Comic Vine issue URL")
        data = self.get_json(issue_api_url,
                             params={"api_key": self.key, "format": "json",
                                     "field_list": "person_credits"})
        writers, artists = split_credits(
            (data.get("results") or {}).get("person_credits", []))
        return (", ".join(writers) or None, ", ".join(artists) or None)

def split_credits(person_credits):
    """Split issue credits into writers and illustrators.

    Illustrator is deliberately NARROW: penciler and artist only. Comic Vine
    roles are comma-joined free text ("penciler, inker, cover"), and the full
    vocabulary also includes inker, colorist, cover, letterer and editor.
    Counting all of those would list six-plus names for a mainstream issue, so
    the column answers "who drew this", not "full art credits". Note this
    drops cover-only artists, the single most common credit.
    """
    writers, artists = [], []
    for person in person_credits or []:
        roles = (person.get("role") or "").lower()
        if "writer" in roles:
            writers.append(person["name"])
        if "artist" in roles or "penciler" in roles:
            artists.append(person["name"])
    return writers, artists
