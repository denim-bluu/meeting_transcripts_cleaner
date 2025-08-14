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

    def extract_topics(self, chunk_results: list[dict]) -> list[str]:
        """Extract unique topics from all chunks."""
        all_topics = []
        for result in chunk_results:
            all_topics.extend(result.get("topics", []))

        # Simple deduplication (could be improved with LLM)
        unique_topics = list(set(all_topics))
        logger.info("Topics extracted", unique_topics=unique_topics)
        return unique_topics

    def group_by_topic(
        self, chunk_results: list[dict], topics: list[str]
    ) -> dict[str, list[dict]]:
        """Group chunk results by topic."""
        topic_groups = defaultdict(list)

        for result in chunk_results:
            chunk_topics = result.get("topics", [])
            for topic in topics:
                # Simple matching - assign chunk to topic if any overlap
                if any(
                    topic.lower() in ct.lower() or ct.lower() in topic.lower()
                    for ct in chunk_topics
                ):
                    topic_groups[topic].append(result)

        return dict(topic_groups)

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
