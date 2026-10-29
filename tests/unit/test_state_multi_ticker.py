"""Tests for multi-ticker AgentState creation and reducer merges."""


from app.graph.state import (
    create_initial_state,
    create_initial_state_multi,
    merge_dicts,
)


class TestCreateInitialStateMulti:
    """Test multi-ticker initial state creation."""

    def test_create_initial_state_multi_basic(self):
        state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4", "VALE3", "ITUB4"],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )
        assert state["manager_id"] == 1
        assert state["company_tickers"] == ["PETR4", "VALE3", "ITUB4"]
        assert state["pipeline_run_id"] == "run-1"
        assert state["morning_note_id"] == "note-1"
        assert state["macro_context"] == {}
        assert state["company_events"] == {}
        assert state["quant_metrics"] == {}
        assert state["risk_flags"] == {}
        assert state["recommendations"] == {}
        assert state["confidence_scores"] == {}
        assert state["data_freshness"] == {}
        assert state["flags"] == []
        assert state["portfolio_risk_flags"] == []
        assert state["portfolio_data_flags"] == []
        assert state["sector_weights"] == {}

    def test_create_initial_state_multi_empty_tickers(self):
        state = create_initial_state_multi(
            manager_id=1,
            company_tickers=[],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )
        assert state["company_tickers"] == []


class TestCreateInitialStateAdapter:
    """Test backward-compatible adapter wrapper."""

    def test_create_initial_state_single_ticker(self):
        state = create_initial_state(
            manager_id=1,
            company_ticker="PETR4",
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )
        assert state["company_tickers"] == ["PETR4"]
        assert state["pipeline_run_id"] == "run-1"

    def test_create_initial_state_with_tickers_list(self):
        state = create_initial_state(
            manager_id=1,
            company_ticker="PETR4",
            company_tickers=["PETR4", "VALE3"],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )
        assert state["company_tickers"] == ["PETR4", "VALE3"]


class TestMergeDictsReducer:
    """Test merge_dicts reducer behavior."""

    def test_merge_dicts_basic(self):
        left = {"a": 1, "b": 2}
        right = {"c": 3}
        merged = merge_dicts(left, right)
        assert merged == {"a": 1, "b": 2, "c": 3}

    def test_merge_dicts_overwrite(self):
        left = {"a": 1}
        right = {"a": 2}
        merged = merge_dicts(left, right)
        assert merged == {"a": 2}

    def test_merge_dicts_empty(self):
        assert merge_dicts({}, {}) == {}
        assert merge_dicts({"a": 1}, {}) == {"a": 1}
        assert merge_dicts({}, {"b": 2}) == {"b": 2}

    def test_merge_dicts_nested(self):
        left = {"PETR4": {"pl": 10.0}}
        right = {"VALE3": {"pl": 15.0}}
        merged = merge_dicts(left, right)
        assert merged == {"PETR4": {"pl": 10.0}, "VALE3": {"pl": 15.0}}

    def test_merge_dicts_same_key_different_values(self):
        left = {"PETR4": {"pl": 10.0}}
        right = {"PETR4": {"ev_ebitda": 8.0}}
        merged = merge_dicts(left, right)
        assert merged == {"PETR4": {"ev_ebitda": 8.0}}


class TestAgentStateStructure:
    """Test AgentState TypedDict structure."""

    def test_agent_state_keys_present(self):
        state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4", "VALE3"],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )
        expected_keys = {
            "pipeline_run_id", "morning_note_id", "manager_id", "company_tickers",
            "macro_context", "company_events", "quant_metrics", "risk_flags",
            "portfolio_risk_flags", "portfolio_data_flags", "sector_weights",
            "morning_note", "recommendations", "confidence_scores",
            "data_freshness", "flags", "recommendation_id",
            "manager_decision", "decision_channel"
        }
        assert set(state.keys()) == expected_keys

    def test_dict_fields_are_empty_dicts(self):
        state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4"],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )
        dict_fields = ["macro_context", "company_events", "quant_metrics",
                       "risk_flags", "recommendations", "confidence_scores",
                       "data_freshness"]
        for field in dict_fields:
            assert isinstance(state[field], dict)
            assert state[field] == {}

    def test_list_fields_are_empty_lists(self):
        state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4"],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )
        list_fields = ["flags", "portfolio_risk_flags", "portfolio_data_flags"]
        for field in list_fields:
            assert isinstance(state[field], list)
            assert state[field] == []


class TestReducerSimulatedParallelWrite:
    """Simulate parallel agent writes merging via merge_dicts."""

    def test_parallel_company_events_merge(self):
        """Simulate CompanyAgent running for PETR4 and VALE3 in parallel."""
        state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4", "VALE3"],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )

        # PETR4 writes
        petr4_events = [{"title": "PETR4 earnings", "summary": "..."}]
        state["company_events"] = merge_dicts(state["company_events"], {"PETR4": petr4_events})

        # VALE3 writes (simulated parallel)
        vale3_events = [{"title": "VALE3 dividend", "summary": "..."}]
        state["company_events"] = merge_dicts(state["company_events"], {"VALE3": vale3_events})

        assert "PETR4" in state["company_events"]
        assert "VALE3" in state["company_events"]
        assert len(state["company_events"]["PETR4"]) == 1
        assert len(state["company_events"]["VALE3"]) == 1

    def test_parallel_quant_metrics_merge(self):
        """Simulate QuantAgent running for multiple tickers."""
        state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4", "VALE3"],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )

        petr4_metrics = {"pl": 10.0, "ev_ebitda": 8.0}
        vale3_metrics = {"pl": 12.0, "ev_ebitda": 7.5}

        state["quant_metrics"] = merge_dicts(state["quant_metrics"], {"PETR4": petr4_metrics})
        state["quant_metrics"] = merge_dicts(state["quant_metrics"], {"VALE3": vale3_metrics})

        assert state["quant_metrics"]["PETR4"]["pl"] == 10.0
        assert state["quant_metrics"]["VALE3"]["pl"] == 12.0

    def test_macro_context_global_key(self):
        """MacroAgent writes to 'global' key."""
        state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4", "VALE3"],
            pipeline_run_id="run-1",
            morning_note_id="note-1"
        )

        macro_output = {"headline": "Selic unchanged", "summary": "..."}
        state["macro_context"] = merge_dicts(state["macro_context"], {"global": macro_output})

        assert state["macro_context"]["global"]["headline"] == "Selic unchanged"
