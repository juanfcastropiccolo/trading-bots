from google.adk.agents import SequentialAgent

from app.adk.agents.data_ingestion import DataIngestionAgent
from app.adk.agents.feature_calc import FeatureCalcAgent
from app.adk.agents.strategy_eval import StrategyEvalAgent
from app.adk.agents.llm_reasoner import create_llm_reasoner
from app.adk.agents.risk_check import RiskCheckAgent
from app.adk.agents.execution import ExecutionAgent
from app.adk.agents.persistence import PersistenceAgent


def create_trading_pipeline() -> SequentialAgent:
    return SequentialAgent(
        name="trading_pipeline",
        description="Sequential trading pipeline: data → features → strategy → LLM → risk → execution → persistence",
        sub_agents=[
            DataIngestionAgent(name="data_ingestion"),
            FeatureCalcAgent(name="feature_calc"),
            StrategyEvalAgent(name="strategy_eval"),
            create_llm_reasoner(),
            RiskCheckAgent(name="risk_check"),
            ExecutionAgent(name="execution"),
            PersistenceAgent(name="persistence"),
        ],
    )
