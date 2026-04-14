"""ContentBlogCrew - Multi-agent pipeline for generating publishable Hedera blog posts."""

from __future__ import annotations

import os
from pathlib import Path

from crewai import Agent, Crew, Process, Task, LLM

from crew.tools.docs_tools import query_hedera_docs
from crew.tools.compliance_tools import get_compliance_rules


_CONFIG_DIR = Path(__file__).parent


def _llm() -> LLM:
    """Create the LLM instance for all agents."""
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    return LLM(
        model=f"openai/{model}",
        temperature=1.0,  # gpt-5-mini only supports temperature=1.0
    )


def _load_yaml(filename: str) -> dict:
    """Load a YAML config file from the crew directory."""
    import yaml

    path = _CONFIG_DIR / filename
    with open(path) as f:
        return yaml.safe_load(f)


class ContentBlogCrew:
    """Multi-agent crew for generating publishable Hedera blog posts.

    Agents:
        1. Transcript Researcher - Extracts technical notes from transcript
        2. Docs Researcher - Queries FAISS for official Hedera docs context
        3. Technical Writer - Writes the blog draft
        4. Editor - Reviews and polishes to publishable quality
        5. Compliance Reviewer - Checks Hedera brand/content guidelines
        6. Publisher - Final formatting + title generation

    Usage:
        crew = ContentBlogCrew()
        result = crew.run(
            transcript_text="...",
            audience="Web3 developers",
            focus="HTS, smart contracts",
            reference_links="",
            titles_count=5,
            output_format="Markdown",
        )
        blog, titles = result["blog"], result["titles"]
    """

    def __init__(
        self,
        include_docs: bool = True,
        include_compliance: bool = True,
    ):
        self.include_docs = include_docs
        self.include_compliance = include_compliance
        self._agents_config = _load_yaml("agents.yaml")
        self._tasks_config = _load_yaml("tasks.yaml")
        self._llm = _llm()

    # ── Agents ──────────────────────────────────────────────────────

    def _transcript_researcher(self) -> Agent:
        cfg = self._agents_config["transcript_researcher"]
        return Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            llm=self._llm,
            allow_delegation=False,
            max_iter=2,
            verbose=True,
        )

    def _docs_researcher(self) -> Agent:
        cfg = self._agents_config["docs_researcher"]
        return Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            tools=[query_hedera_docs],
            llm=self._llm,
            allow_delegation=False,
            max_iter=2,
            verbose=True,
        )

    def _technical_writer(self) -> Agent:
        cfg = self._agents_config["technical_writer"]
        return Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            llm=self._llm,
            allow_delegation=False,
            max_iter=1,
            verbose=True,
        )

    def _editor(self) -> Agent:
        cfg = self._agents_config["editor"]
        return Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            llm=self._llm,
            allow_delegation=False,
            max_iter=1,
            verbose=True,
        )

    def _compliance_reviewer(self) -> Agent:
        cfg = self._agents_config["compliance_reviewer"]
        return Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            tools=[get_compliance_rules],
            llm=self._llm,
            allow_delegation=False,
            max_iter=2,
            verbose=True,
        )

    def _publisher(self) -> Agent:
        cfg = self._agents_config["publisher"]
        return Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            llm=self._llm,
            allow_delegation=False,
            max_iter=1,
            verbose=True,
        )

    # ── Tasks ───────────────────────────────────────────────────────

    def _build_tasks(self, agents: dict[str, Agent]) -> list[Task]:
        """Build the task list dynamically based on included agents."""
        tasks = []

        # 1. Transcript research (always)
        cfg = self._tasks_config["transcript_research_task"]
        transcript_task = Task(
            description=cfg["description"],
            expected_output=cfg["expected_output"],
            agent=agents["transcript_researcher"],
        )
        tasks.append(transcript_task)

        # 2. Docs research (optional)
        docs_task = None
        if self.include_docs and "docs_researcher" in agents:
            cfg = self._tasks_config["docs_research_task"]
            docs_task = Task(
                description=cfg["description"],
                expected_output=cfg["expected_output"],
                agent=agents["docs_researcher"],
                context=[transcript_task],
            )
            tasks.append(docs_task)

        # 3. Writing
        cfg = self._tasks_config["writing_task"]
        writer_context = [docs_task or transcript_task]
        if docs_task and transcript_task not in writer_context:
            writer_context.insert(0, transcript_task)
        writing_task = Task(
            description=cfg["description"],
            expected_output=cfg["expected_output"],
            agent=agents["technical_writer"],
            context=writer_context,
        )
        tasks.append(writing_task)

        # 4. Editing
        cfg = self._tasks_config["editing_task"]
        editing_task = Task(
            description=cfg["description"],
            expected_output=cfg["expected_output"],
            agent=agents["editor"],
            context=[transcript_task, docs_task or transcript_task, writing_task],
        )
        tasks.append(editing_task)

        # 5. Compliance (optional)
        compliance_task = None
        if self.include_compliance and "compliance_reviewer" in agents:
            cfg = self._tasks_config["compliance_review_task"]
            compliance_task = Task(
                description=cfg["description"],
                expected_output=cfg["expected_output"],
                agent=agents["compliance_reviewer"],
                context=[transcript_task, editing_task],
            )
            tasks.append(compliance_task)

        # 6. Publishing
        cfg = self._tasks_config["publishing_task"]
        pub_context = [compliance_task or editing_task]
        publishing_task = Task(
            description=cfg["description"],
            expected_output=cfg["expected_output"],
            agent=agents["publisher"],
            context=pub_context,
        )
        tasks.append(publishing_task)

        return tasks

    # ── Crew ────────────────────────────────────────────────────────

    def build_crew(self) -> Crew:
        """Build the crew with the configured agents and tasks."""
        agents = {
            "transcript_researcher": self._transcript_researcher(),
            "technical_writer": self._technical_writer(),
            "editor": self._editor(),
            "publisher": self._publisher(),
        }

        if self.include_docs:
            agents["docs_researcher"] = self._docs_researcher()

        if self.include_compliance:
            agents["compliance_reviewer"] = self._compliance_reviewer()

        tasks = self._build_tasks(agents)

        return Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def run(
        self,
        transcript_text: str,
        audience: str = "Web3 developers and Hedera builders",
        focus: str = "Not specified",
        reference_links: str = "",
        titles_count: int = 5,
        output_format: str = "Markdown",
    ) -> dict:
        """Run the full blog generation pipeline.

        Returns:
            dict with keys: blog, titles, status
        """
        crew = self.build_crew()

        inputs = {
            "transcript_text": transcript_text[:80000],  # Cap to avoid context overflow
            "audience": audience,
            "focus": focus or "Not specified",
            "reference_links": reference_links or "None provided",
            "titles_count": titles_count,
            "output_format": output_format,
        }

        result = crew.kickoff(inputs=inputs)
        output = str(result)

        # Parse output: blog + titles + tags separated by ---TITLES--- and ---TAGS---
        blog, titles, tags = self._parse_publisher_output(output)

        agent_count = len(crew.agents)
        task_count = len(crew.tasks)

        status = (
            f"Agents: {agent_count}. Tasks: {task_count}. "
            f"Docs enrichment: {'on' if self.include_docs else 'off'}. "
            f"Compliance check: {'on' if self.include_compliance else 'off'}. "
            f"Output format: {output_format}. "
            f"Tags: {len(tags)}."
        )

        return {
            "blog": blog,
            "titles": titles,
            "tags": tags,
            "status": status,
        }

    @staticmethod
    def _parse_publisher_output(output: str) -> tuple[str, str, list[str]]:
        """Parse the publisher's output into (blog, titles, tags).

        Expected format:
            {blog markdown}
            ---TITLES---
            {title 1}
            {title 2}
            ...
            ---TAGS---
            {tag 1}
            {tag 2}
            ...

        All separators are optional - missing sections return empty defaults.
        """
        # Split on ---TAGS--- first (innermost separator)
        if "---TAGS---" in output:
            head, tags_section = output.split("---TAGS---", 1)
            tags = [
                line.strip().lstrip("-").strip().lower().replace(" ", "-")
                for line in tags_section.strip().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            # Cap to 5 (Medium's limit) and strip empty
            tags = [t for t in tags if t][:5]
        else:
            head = output
            tags = []

        # Then split head on ---TITLES---
        if "---TITLES---" in head:
            blog, titles_section = head.split("---TITLES---", 1)
            blog = blog.strip()
            titles = titles_section.strip()
        else:
            blog = head.strip()
            titles = ""

        return blog, titles, tags
