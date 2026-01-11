"""
Phase 3 Usage Examples - Recommendation Engine

Run examples:
    python examples/phase3_usage.py
"""

import asyncio
import httpx
from typing import List, Dict

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
EXAMPLE_STEAM_ID = "76561198375287205"  # Replace with your Steam ID


async def example_1_basic_recommendations():
    """Example 1: Get Basic Recommendations"""
    print("\n" + "="*80)
    print("Example 1: Basic Personalized Recommendations")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        print("\n1. Getting top 10 recommendations...")
        
        response = await client.get(
            f"{BASE_URL}/recommendations/{EXAMPLE_STEAM_ID}",
            params={"limit": 10}
        )
        
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.json())
            return
        
        recommendations = response.json()
        
        print(f"\n✓ Received {len(recommendations)} recommendations\n")
        
        for i, rec in enumerate(recommendations[:5], 1):
            price = f"${rec['price']:.2f}" if rec['price'] else "Free"
            print(f"{i}. {rec['name']}")
            print(f"   Score: {rec['final_score']:.3f} | Similarity: {rec['similarity_score']:.3f}")
            print(f"   Price: {price}")
            print(f"   Why: {rec.get('explanation', 'N/A')}")
            print()


async def example_2_filtered_recommendations():
    """Example 2: Filtered Recommendations (Indie + Price)"""
    print("\n" + "="*80)
    print("Example 2: Indie Games Under $10")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        print("\n1. Getting indie recommendations under $10...")
        
        response = await client.get(
            f"{BASE_URL}/recommendations/{EXAMPLE_STEAM_ID}",
            params={
                "limit": 10,
                "indie_only": True,
                "max_price": 10.0
            }
        )
        
        recommendations = response.json()
        
        print(f"\n✓ Found {len(recommendations)} affordable indie games\n")
        
        for i, rec in enumerate(recommendations, 1):
            price = f"${rec['price']:.2f}" if rec['price'] else "Free"
            print(f"{i}. {rec['name']} - {price}")
            print(f"   Genres: {', '.join(rec['genres'][:3])}")
            print()


async def example_3_user_profile():
    """Example 3: View User Preference Profile"""
    print("\n" + "="*80)
    print("Example 3: User Preference Profile")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        print("\n1. Fetching user profile...")
        
        response = await client.get(
            f"{BASE_URL}/recommendations/{EXAMPLE_STEAM_ID}/profile"
        )
        
        profile = response.json()
        
        print(f"\n✓ Profile Analysis:")
        print(f"   Games analyzed: {profile['total_games_analyzed']}")
        print(f"   Owned games: {profile['owned_games_count']}")
        print(f"   Avg playtime: {profile['avg_playtime_hours']:.1f} hours")
        
        print(f"\n   Top Genres:")
        for i, genre in enumerate(profile['top_genres'][:5], 1):
            print(f"     {i}. {genre}")
        
        print(f"\n   Top Tags:")
        for i, tag in enumerate(profile['top_tags'][:5], 1):
            print(f"     {i}. {tag}")


async def example_4_similar_games():
    """Example 4: Find Similar Games"""
    print("\n" + "="*80)
    print("Example 4: Find Games Similar to Hades")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        hades_id = 1145360  # Hades game ID
        
        print(f"\n1. Finding games similar to game ID {hades_id}...")
        
        response = await client.get(
            f"{BASE_URL}/recommendations/{EXAMPLE_STEAM_ID}/similar/{hades_id}",
            params={"limit": 5}
        )
        
        if response.status_code != 200:
            print(f"Error: Game not found or error occurred")
            return
        
        similar_games = response.json()
        
        print(f"\n✓ Found {len(similar_games)} similar games\n")
        
        for i, game in enumerate(similar_games, 1):
            price = f"${game['price']:.2f}" if game['price'] else "Free"
            print(f"{i}. {game['name']}")
            print(f"   Similarity: {game['similarity_score']:.3f}")
            print(f"   Price: {price}")
            print(f"   Genres: {', '.join(game['genres'][:3])}")
            print()


async def example_5_high_quality_recommendations():
    """Example 5: High-Quality Recommendations Only"""
    print("\n" + "="*80)
    print("Example 5: High-Quality Recommendations (Min Similarity 0.3)")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        print("\n1. Getting high-confidence recommendations...")
        
        response = await client.get(
            f"{BASE_URL}/recommendations/{EXAMPLE_STEAM_ID}",
            params={
                "limit": 20,
                "min_similarity": 0.3  # Higher threshold
            }
        )
        
        recommendations = response.json()
        
        print(f"\n✓ Found {len(recommendations)} high-quality matches\n")
        
        if recommendations:
            avg_score = sum(r['similarity_score'] for r in recommendations) / len(recommendations)
            print(f"Average similarity: {avg_score:.3f}")
            print("\nTop 5:")
            
            for i, rec in enumerate(recommendations[:5], 1):
                print(f"{i}. {rec['name']} (similarity: {rec['similarity_score']:.3f})")
        else:
            print("No games meet the high similarity threshold")
            print("Try lowering min_similarity or playing more games to build a better profile")


async def example_6_compare_filters():
    """Example 6: Compare Different Filters"""
    print("\n" + "="*80)
    print("Example 6: Comparing Filter Results")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        # Test different filters
        filters = [
            {"name": "All Games", "params": {"limit": 10}},
            {"name": "Indie Only", "params": {"limit": 10, "indie_only": True}},
            {"name": "Under $5", "params": {"limit": 10, "max_price": 5.0}},
            {"name": "Free Games", "params": {"limit": 10, "max_price": 0.0}},
        ]
        
        print("\nComparing different filters:\n")
        
        for filter_config in filters:
            response = await client.get(
                f"{BASE_URL}/recommendations/{EXAMPLE_STEAM_ID}",
                params=filter_config["params"]
            )
            
            recs = response.json()
            
            if recs:
                avg_score = sum(r['final_score'] for r in recs) / len(recs)
                avg_price = sum(r['price'] or 0 for r in recs) / len(recs)
                
                print(f"{filter_config['name']}:")
                print(f"  Count: {len(recs)}")
                print(f"  Avg Score: {avg_score:.3f}")
                print(f"  Avg Price: ${avg_price:.2f}")
                print(f"  Top game: {recs[0]['name']}")
                print()


async def example_7_build_game_list():
    """Example 7: Build a Curated Game List"""
    print("\n" + "="*80)
    print("Example 7: Building a Curated Game List")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        print("\nCreating a mixed recommendation list:\n")
        
        # Get different categories
        categories = {
            "Top Picks": {"limit": 3, "min_similarity": 0.3},
            "Indie Gems": {"limit": 3, "indie_only": True, "max_price": 15.0},
            "Free to Play": {"limit": 2, "max_price": 0.0},
        }
        
        curated_list = []
        
        for category, params in categories.items():
            response = await client.get(
                f"{BASE_URL}/recommendations/{EXAMPLE_STEAM_ID}",
                params=params
            )
            
            recs = response.json()
            
            print(f"📌 {category}")
            for rec in recs:
                price = f"${rec['price']:.2f}" if rec['price'] else "Free"
                print(f"   • {rec['name']} - {price}")
            print()
            
            curated_list.extend(recs)
        
        print(f"Total curated games: {len(curated_list)}")


async def run_all_examples():
    """Run all examples in sequence"""
    print("\n" + "="*100)
    print("PHASE 3 USAGE EXAMPLES")
    print("Steam Game Recommender - ML-Based Recommendations")
    print("="*100)
    
    print(f"\nUsing Steam ID: {EXAMPLE_STEAM_ID}")
    print("(Replace with your Steam ID in the script)")
    
    try:
        await example_1_basic_recommendations()
        await example_2_filtered_recommendations()
        await example_3_user_profile()
        await example_4_similar_games()
        await example_5_high_quality_recommendations()
        await example_6_compare_filters()
        await example_7_build_game_list()
        
        print("\n" + "="*100)
        print("✓ ALL EXAMPLES COMPLETED SUCCESSFULLY!")
        print("="*100)
        print("\nYou now know how to:")
        print("  1. Get personalized recommendations")
        print("  2. Filter by price and indie status")
        print("  3. View user preference profiles")
        print("  4. Find similar games")
        print("  5. Adjust quality thresholds")
        print("  6. Build curated game lists")
        print("\n🎉 Phase 3 Complete! Your recommendation engine is working!")
        
    except Exception as e:
        print(f"\n✗ Error running examples: {e}")
        print("\nMake sure:")
        print("  1. Server is running: uvicorn app.main:app --reload")
        print("  2. You've synced a library with playtime data")
        print("  3. Database has games from Phase 1")


if __name__ == "__main__":
    asyncio.run(run_all_examples())