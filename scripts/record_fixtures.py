"""Re-record ATS fixtures. Run manually; not part of the test suite."""
import json
import pathlib
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 Chrome/131.0"}
OUT = pathlib.Path(__file__).parent.parent / "tests" / "fixtures"

TARGETS = {
    "greenhouse_jfrog.json":
        "https://boards-api.greenhouse.io/v1/boards/jfrog/jobs?content=true",
    "ashby_lemonade.json":
        "https://api.ashbyhq.com/posting-api/job-board/lemonade",
    "lever_walkme.json":
        "https://api.lever.co/v0/postings/walkme?mode=json",
    "smartrecruiters_armis.json":
        "https://api.smartrecruiters.com/v1/companies/armis/postings?limit=100",
}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.loads(f.read())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in TARGETS.items():
        data = get(url)
        (OUT / name).write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print(f"wrote {name}")

    # SmartRecruiters descriptions need a second call; record one detail payload.
    listing = json.loads((OUT / "smartrecruiters_armis.json").read_text())
    job_id = listing["content"][0]["id"]
    detail = get(
        f"https://api.smartrecruiters.com/v1/companies/armis/postings/{job_id}"
    )
    (OUT / "smartrecruiters_armis_detail.json").write_text(
        json.dumps(detail, indent=1, ensure_ascii=False)
    )
    print("wrote smartrecruiters_armis_detail.json")


if __name__ == "__main__":
    main()
