"""YouTube Data API でモデル動画のコメントを取得する。

APIキーは環境のネットワークシークレット（www.googleapis.com に X-Goog-Api-Key ヘッダー）で付くため、
このスクリプトはキーを持たない。
各動画の上位コメント（relevance 順）を最大 MAX_PAGES×100 件、02_リサーチ/コメント生データ/<動画ID>.json に保存する。
コメントは他人の投稿なので、生データは git に入れない（.gitignore 済み）。
"""
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from make_analysis_sheet import VIDEOS  # noqa: E402

API = "https://www.googleapis.com/youtube/v3/"
MAX_PAGES = 2
OUT = os.path.join(os.path.dirname(__file__), "..", "02_リサーチ", "コメント生データ")


def get(endpoint, **params):
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main():
    os.makedirs(OUT, exist_ok=True)
    ids = [vid for _, vid, _ in VIDEOS]
    stats = {}
    for i in range(0, len(ids), 50):
        for item in get("videos", part="statistics,snippet", id=",".join(ids[i:i + 50]))["items"]:
            stats[item["id"]] = {**item["statistics"], "publishedAt": item["snippet"]["publishedAt"]}
    for ch, vid, title in VIDEOS:
        comments, token = [], None
        for _ in range(MAX_PAGES):
            params = dict(part="snippet", videoId=vid, maxResults=100, order="relevance", textFormat="plainText")
            if token:
                params["pageToken"] = token
            data = get("commentThreads", **params)
            for t in data.get("items", []):
                s = t["snippet"]["topLevelComment"]["snippet"]
                comments.append({"text": s["textDisplay"], "likes": s["likeCount"],
                                 "replies": t["snippet"]["totalReplyCount"], "publishedAt": s["publishedAt"]})
            token = data.get("nextPageToken")
            if not token:
                break
        with open(os.path.join(OUT, f"{vid}.json"), "w", encoding="utf-8") as f:
            json.dump({"channel": ch, "videoId": vid, "title": title, "stats": stats.get(vid, {}),
                       "comments": comments}, f, ensure_ascii=False, indent=1)
        print(ch[:6], vid, stats.get(vid, {}).get("commentCount"), len(comments))


if __name__ == "__main__":
    main()
