"""
AdEngineAI — Publisher Formatters
====================================
Per-platform content formatting.
Each platform has different requirements for titles, descriptions, tags.

To change formatting rules per platform: edit this file only.
Publisher agent code stays untouched.
"""

from director.agent import Script


def format_youtube(script: Script, video_url: str) -> dict:
    """
    Formats content for YouTube upload.
    YouTube requires: title, description, tags, category, privacy.
    """
    # Build description with full script + hashtags
    description = (
        f"{script.script}\n\n"
        f"{'─' * 40}\n\n"
        f"{' '.join(script.hashtags[:15])}"
    )

    # YouTube title max 100 chars
    title = script.ad_headline[:100] if script.ad_headline else script.hook_line[:100]

    return {
        "title": title,
        "description": description[:5000],   # YouTube max
        "tags": [h.replace("#", "") for h in script.hashtags[:15]],
        "category_id": "22",        # People & Blogs — best for ads
        "privacy": "public",
        "video_url": video_url,
    }


def format_instagram(script: Script, video_url: str) -> dict:
    """
    Formats content for Instagram Reels.
    Instagram requires: caption, video_url.
    Max caption: 2200 chars.
    """
    caption = f"{script.caption_instagram}\n\n{' '.join(script.hashtags[:30])}"

    return {
        "caption": caption[:2200],
        "video_url": video_url,
        "media_type": "REELS",
    }


def format_facebook(script: Script, video_url: str) -> dict:
    """
    Formats content for Facebook video post.
    """
    description = (
        f"{script.caption_instagram}\n\n"
        f"{script.ad_description}\n\n"
        f"{' '.join(script.hashtags[:10])}"
    )

    return {
        "description": description[:63206],  # Facebook max
        "title": script.ad_headline[:255],
        "video_url": video_url,
    }


def format_linkedin(script: Script, video_url: str) -> dict:
    """
    Formats content for LinkedIn video post.
    LinkedIn requires professional tone — uses linkedin-specific caption.
    """
    text = (
        f"{script.caption_linkedin}\n\n"
        f"{script.ad_description}\n\n"
        f"{' '.join(script.hashtags[:5])}"   # LinkedIn — fewer hashtags
    )

    return {
        "text": text[:3000],        # LinkedIn max
        "video_url": video_url,
        "visibility": "PUBLIC",
    }


def format_tiktok(script: Script, video_url: str) -> dict:
    """
    Formats content for TikTok video post.
    TikTok caption max: 2200 chars, max 5 hashtags recommended.
    """
    caption = f"{script.caption_tiktok} {' '.join(script.hashtags[:5])}"

    return {
        "caption": caption[:2200],
        "video_url": video_url,
        "privacy_level": "PUBLIC_TO_EVERYONE",
        "disable_duet": False,
        "disable_comment": False,
    }