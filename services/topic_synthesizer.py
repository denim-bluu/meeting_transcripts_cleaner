from collections import defaultdict

from pydantic_ai import Agent
import structlog

logger = structlog.get_logger(__name__)


class TopicSynthesizer:
    """
    Synthesize chunk results into topic-based markdown summaries.

    Responsibilities:
    - Group chunk results by topic
    - Generate coherent markdown for each topic
    - Combine into final summary with proper headers
    - Preserve technical details without quotes

    Expected behavior:
    - One LLM call per unique topic (3-5 topics typical)
    - Returns markdown with # headers and - bullets
    - Maintains technical accuracy
    """

    def __init__(self, api_key: str, model: str = "o3-mini"):
        self.agent = Agent(f"openai:{model}")
        logger.info("TopicSynthesizer initialized", model=model)

    async def extract_and_cluster_topics(self, chunk_results: list[dict]) -> list[str]:
        """Extract topics and cluster them into 5-10 major themes."""
        # First extract all topics
        all_topics = []
        for result in chunk_results:
            all_topics.extend(result.get("topics", []))

        unique_topics = list(set(all_topics))
        logger.info("Raw topics extracted", count=len(unique_topics))

        # If we have too many topics, cluster them into major themes
        if len(unique_topics) > 15:
            logger.info(
                "Clustering topics into major themes", original_count=len(unique_topics)
            )
            clustered_topics = await self._cluster_topics_into_themes(unique_topics)
            logger.info("Topics clustered", clustered_count=len(clustered_topics))
            return clustered_topics
        else:
            logger.info("Using original topics", count=len(unique_topics))
            return unique_topics

    def extract_topics(self, chunk_results: list[dict]) -> list[str]:
        """Legacy method for backward compatibility - returns raw topics."""
        all_topics = []
        for result in chunk_results:
            all_topics.extend(result.get("topics", []))
        return list(set(all_topics))

    async def _cluster_topics_into_themes(self, topics: list[str]) -> list[str]:
        """Use LLM to cluster micro-topics into 5-10 major themes."""
        prompt = f"""
        You have {len(topics)} micro-topics from a meeting transcript. Cluster them into 5-8 major themes.

        Micro-topics:
        {chr(10).join(f"- {topic}" for topic in topics)}

        Group these into major themes that represent the main discussion areas.
        Return ONLY the major theme names, one per line, like:

        Model Development and Architecture
        Performance Analysis and Backtesting
        Market Analysis and Regional Considerations
        API Development and Customization
        Data Quality and Methodology

        Focus on:
        - Grouping related technical concepts together
        - Creating 5-8 broad themes (not more than 8)
        - Using clear, descriptive theme names
        - Covering all important micro-topics
        """

        result = await self.agent.run(prompt)

        # Parse the result to get clean theme names
        theme_lines = [
            line.strip() for line in result.output.strip().split("\n") if line.strip()
        ]
        # Filter out any empty lines or formatting artifacts
        themes = [
            line
            for line in theme_lines
            if line and not line.startswith("-") and not line.startswith("*")
        ]

        logger.info("Generated major themes", themes=themes)
        return themes[:8]  # Ensure we don't exceed 8 themes

    def group_by_topic(
        self, chunk_results: list[dict], topics: list[str]
    ) -> dict[str, list[dict]]:
        """Group chunk results by topic with improved matching."""
        topic_groups = defaultdict(list)

        for result in chunk_results:
            chunk_topics = result.get("topics", [])
            for major_topic in topics:
                # Improved matching - use keywords and semantic similarity
                topic_matched = False

                for chunk_topic in chunk_topics:
                    # Check for exact or partial matches
                    if (
                        major_topic.lower() in chunk_topic.lower()
                        or chunk_topic.lower() in major_topic.lower()
                        or self._topics_are_related(major_topic, chunk_topic)
                    ):
                        topic_groups[major_topic].append(result)
                        topic_matched = True
                        break

                # If no match found but chunk has high importance, check for keyword overlap
                if not topic_matched and result.get("importance_score", 0) >= 7:
                    if self._keywords_overlap(major_topic, chunk_topics):
                        topic_groups[major_topic].append(result)

        logger.info(
            "Grouped chunks by topics",
            topics_with_content=len(
                [t for t, chunks in topic_groups.items() if chunks]
            ),
            total_chunks_grouped=sum(len(chunks) for chunks in topic_groups.values()),
        )

        return dict(topic_groups)

    def _topics_are_related(self, major_topic: str, chunk_topic: str) -> bool:
        """Check if topics are semantically related using keyword overlap."""
        # Convert to lowercase and split into words
        major_words = set(major_topic.lower().split())
        chunk_words = set(chunk_topic.lower().split())

        # Remove common words
        common_words = {
            "and",
            "the",
            "of",
            "in",
            "for",
            "with",
            "on",
            "to",
            "from",
            "by",
            "at",
        }
        major_words -= common_words
        chunk_words -= common_words

        # Check for significant word overlap (at least 1 meaningful word)
        overlap = major_words & chunk_words
        return (
            len(overlap) > 0
            and len(overlap) / max(len(major_words), len(chunk_words)) > 0.2
        )

    def _keywords_overlap(self, major_topic: str, chunk_topics: list[str]) -> bool:
        """Check if major topic keywords overlap with any chunk topics."""
        major_keywords = set(major_topic.lower().split())

        for chunk_topic in chunk_topics:
            chunk_keywords = set(chunk_topic.lower().split())
            if major_keywords & chunk_keywords:
                return True
        return False

    async def synthesize_topic(self, topic: str, relevant_chunks: list[dict]) -> str:
        """Synthesize all content for a specific topic."""
        # Combine key points from high-importance chunks
        important_points = []
        for chunk in relevant_chunks:
            if chunk["importance_score"] >= 6:  # High importance threshold
                important_points.extend(chunk["key_points"])

        if not important_points:
            return f"# {topic}\n- No significant details available\n"

        prompt = f"""
        Create a comprehensive summary for the topic "{topic}" based on these key points:

        {chr(10).join(f"- {point}" for point in important_points)}

        Format as markdown:
        # {topic}
        - Comprehensive point with full context
        - Another detailed point
          - Sub-detail if relevant

        Requirements:
        - Include all important technical details
        - Use bullet points for clarity
        - Maintain professional tone
        - Group related information
        """

        result = await self.agent.run(prompt)
        return result.output

    async def create_full_summary(self, chunk_results: list[dict]) -> str:
        """Create complete markdown summary organized by topics."""
        topics = self.extract_topics(chunk_results)
        topic_groups = self.group_by_topic(chunk_results, topics)

        topic_summaries = []
        for topic in topics:
            if topic in topic_groups:
                summary = await self.synthesize_topic(topic, topic_groups[topic])
                topic_summaries.append(summary)

        # Handle ungrouped content
        all_assigned_chunks = set()
        for chunks in topic_groups.values():
            all_assigned_chunks.update(id(c) for c in chunks)

        ungrouped = [c for c in chunk_results if id(c) not in all_assigned_chunks]
        if ungrouped:
            other_summary = await self.synthesize_topic("Other Discussion", ungrouped)
            topic_summaries.append(other_summary)

        return "\n\n".join(topic_summaries)
