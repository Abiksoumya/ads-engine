"""
Test fal.ai Kling Tool
Run: python tests/test_fal_kling.py

Tests:
  1. Mock mode (no API key)
  2. Real generation with text prompt
  3. Real generation with image + text
  4. All scenes from a video brief
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from mcp_tools.fal_kling_tools import FalKlingTool


async def test_mock_mode():
    print("\n" + "="*60)
    print("TEST 1 — Mock Mode (no API key)")
    print("="*60)

    tool = FalKlingTool(api_key="")

    result = await tool.generate_scene(
        prompt="Shoe floating in forest, cinematic",
        duration=5,
        aspect_ratio="9:16",
        hook_type="problem",
        scene_number=1,
    )

    print(f"Is mock:   {result.is_mock}")
    print(f"Video URL: {result.video_url}")
    print(f"Duration:  {result.duration_secs}s")
    assert result.is_mock is True
    print("PASS ✅")


async def test_text_to_video():
    print("\n" + "="*60)
    print("TEST 2 — Text to Video (real API)")
    print("="*60)

    api_key = os.getenv("FAL_API_KEY", "")
    if not api_key:
        print("SKIP — FAL_API_KEY not set in .env")
        return

    tool = FalKlingTool(api_key=api_key)

    result = await tool.generate_scene(
        prompt=(
            "Software engineer at desk late at night, stressed expression, "
            "multiple monitors showing code errors, empty coffee cups, "
            "dim blue office lighting, slow zoom in, cinematic quality, "
            "4K, professional advertisement style"
        ),
        duration=5,
        aspect_ratio="9:16",
        hook_type="problem",
        scene_number=1,
        image_url=None,
    )

    print(f"Success:   {result.success}")
    print(f"Is mock:   {result.is_mock}")
    print(f"Video URL: {result.video_url}")
    print(f"Duration:  {result.duration_secs}s")
    print(f"Error:     {result.error}")

    if result.success:
        print("PASS ✅")
    else:
        print(f"FAIL ❌ — {result.error}")


async def test_image_to_video():
    print("\n" + "="*60)
    print("TEST 3 — Image to Video (real API)")
    print("="*60)

    api_key = os.getenv("FAL_API_KEY", "")
    if not api_key:
        print("SKIP — FAL_API_KEY not set in .env")
        return

    tool = FalKlingTool(api_key=api_key)

    # Using a public test image
    result = await tool.generate_scene(
        prompt=(
            "White sneaker shoe floating in eucalyptus forest, "
            "cool misty atmosphere, slow cinematic rotation, "
            "soft green light filtering through leaves, "
            "cinematic quality, 4K, professional product advertisement"
        ),
        duration=5,
        aspect_ratio="9:16",
        hook_type="problem",
        scene_number=2,
        image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800",
    )

    print(f"Success:   {result.success}")
    print(f"Is mock:   {result.is_mock}")
    print(f"Video URL: {result.video_url}")
    print(f"Duration:  {result.duration_secs}s")
    print(f"Error:     {result.error}")

    if result.success:
        print("PASS ✅")
        print(f"\nOpen this URL to watch the video:\n{result.video_url}")
    else:
        print(f"FAIL ❌ — {result.error}")


async def test_all_ratios():
    print("\n" + "="*60)
    print("TEST 4 — All 3 Aspect Ratios")
    print("="*60)

    api_key = os.getenv("FAL_API_KEY", "")
    if not api_key:
        print("SKIP — FAL_API_KEY not set in .env")
        return

    tool = FalKlingTool(api_key=api_key)

    result = await tool.generate_for_ratio(
        prompt="Person walking confidently...",
        duration=5,
        hook_type="emotional",
        scene_number=3,
        aspect_ratio="9:16",   # user selected
        image_url=None,
    )

    print(f"9:16:  {result.video_url_9x16}")
    print(f"1:1:   {result.video_url_1x1}")
    print(f"16:9:  {result.video_url_16x9}")
    print(f"Mock:  {result.is_mock}")

    if result.video_url_9x16:
        print("PASS ✅")
    else:
        print("FAIL ❌")


async def test_brief_scenes():
    print("\n" + "="*60)
    print("TEST 5 — Generate All Scenes from Brief")
    print("="*60)

    tool = FalKlingTool(api_key="")  # mock mode

    scenes = [
        {
            "scene_number": 1,
            "duration": 5,
            "kling_prompt": "Hot city pavement, heat shimmer, close up of feet walking",
            "product_image_url": None,
        },
        {
            "scene_number": 2,
            "duration": 5,
            "kling_prompt": "Shoe floating in eucalyptus forest, cool mist, cinematic",
            "product_image_url": "https://example.com/shoe.jpg",
        },
        {
            "scene_number": 3,
            "duration": 5,
            "kling_prompt": "Clean studio product shot, CTA text overlay",
            "product_image_url": "https://example.com/shoe.jpg",
        },
    ]

    results = await tool.generate_scenes_for_brief(
        scenes=scenes,
        hook_type="problem",
        aspect_ratio="9:16",
    )

    for r in results:
        print(f"Scene {r.scene_number}: {r.video_url} | mock={r.is_mock}")

    assert len(results) == 3
    print("PASS ✅")


async def main():
    await test_mock_mode()
    await test_text_to_video()
    await test_image_to_video()
    await test_all_ratios()
    await test_brief_scenes()

    print("\n" + "="*60)
    print("fal.ai Kling tests complete")
    print("="*60)


asyncio.run(main())