"""
Test Visual Director Agent
Run: python test_visual_director.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


from visual_director.agent import VisualDirectorAgent


from dotenv import load_dotenv
load_dotenv()



async def test_campaign_brief():
    print("\n" + "="*60)
    print("TEST 1 — Campaign Brief (Product Ad)")
    print("="*60)

    agent = VisualDirectorAgent()

    result = await agent.campaign_brief(
        hook_type="problem",
        hook_line="Your feet are on fire by 3pm",
        script_text=(
            "Your feet feel like they're wrapped in plastic bags by 3pm. "
            "You bought casual shoes but they're furnace-hot and heavy. "
            "Allbirds Tree Runners are made from eucalyptus fiber with natural "
            "micro-channels that pull heat away. 50,000 men already switched. "
            "Try them free for 30 days."
        ),
        product_name="Allbirds Tree Runner",
        product_description="Sustainable shoe made from eucalyptus fiber, ultra lightweight and breathable",
        product_images=[
            "https://cdn.allbirds.com/image/upload/shoe.jpg",
        ],
        scene_count=3,
        user_preferences={
            "tone": "dramatic_to_relief",
            "pacing": "medium",
        },
    )

    print(f"\nSuccess: {result.success}")
    print(f"Tone: {result.tone}")
    print(f"Palette: {result.color_palette}")
    print(f"Pacing: {result.pacing}")
    print(f"Duration: {result.duration_secs}s")
    print(f"Scenes: {result.scene_count}")
    print(f"\nVoiceover:\n{result.voiceover_script}")
    print(f"\nScenes:")
    for scene in result.scenes:
        print(f"\n  Scene {scene.scene_number}:")
        print(f"    Background: {scene.background}")
        print(f"    Action:     {scene.action}")
        print(f"    Color:      {scene.color_mood}")
        print(f"    Camera:     {scene.camera}")
        print(f"    Overlay:    {scene.text_overlay}")
        print(f"    Product img: {scene.use_product_image}")
        print(f"    Kling prompt: {scene.kling_prompt[:80]}...")

    return result


async def test_creation_brief():
    print("\n" + "="*60)
    print("TEST 2 — Creation Brief (Video Creator)")
    print("="*60)

    agent = VisualDirectorAgent()

    result = await agent.creation_brief(
        user_prompt=(
            "Software engineer working late at night, stressed, "
            "discovers an AI tool that generates videos automatically. "
            "She goes from exhausted to excited and happy."
        ),
        uploaded_images=[],
        scene_count=3,
        user_preferences={
            "tone": "dramatic_to_inspirational",
            "pacing": "medium",
            "background_style": "office_corporate",
        },
    )

    print(f"\nSuccess: {result.success}")
    print(f"Tone: {result.tone}")
    print(f"Palette: {result.color_palette}")
    print(f"Duration: {result.duration_secs}s")
    print(f"\nVoiceover:\n{result.voiceover_script}")
    print(f"\nScenes:")
    for scene in result.scenes:
        print(f"\n  Scene {scene.scene_number}:")
        print(f"    Background: {scene.background}")
        print(f"    Action:     {scene.action}")
        print(f"    Kling prompt: {scene.kling_prompt[:80]}...")

    return result


async def main():
    await test_campaign_brief()
    await test_creation_brief()
    print("\n" + "="*60)
    print("Visual Director tests complete")
    print("="*60)


asyncio.run(main())