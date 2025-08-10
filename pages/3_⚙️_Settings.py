"""
Settings page for Meeting Transcript Cleaner.

This page provides an intuitive interface for configuring AI agent settings,
processing parameters, and confidence thresholds. Configuration changes are
stored in session state and applied to the processing workflow.
"""

import streamlit as st

from utils.config_manager import (
    QUALITY_PRESETS,
    QualityPreset,
    apply_preset,
    clear_config_overrides,
    get_active_preset,
    get_available_openai_models,
    get_merged_agent_config,
    get_merged_confidence_thresholds,
    get_merged_processing_config,
    has_config_overrides,
    set_config_override,
)


def render_preset_section() -> None:
    """Render the quality preset selection section."""
    st.subheader("🎯 Quality Presets")
    st.markdown("Choose a preset configuration optimized for your needs:")

    # Get current active preset
    current_preset = get_active_preset()
    preset_options = list(QualityPreset)

    # Find current index
    current_index = 1
    if current_preset:
        current_index = preset_options.index(current_preset)

    # Preset selector
    selected_preset = st.selectbox(
        "Select Preset",
        options=preset_options,
        index=current_index,
        format_func=lambda x: x.value,
        help="Presets automatically configure all settings for common use cases",
    )

    # Show preset description
    if selected_preset:
        config = QUALITY_PRESETS[selected_preset]
        st.info(f"**{selected_preset.value}**: {config.description}")

        # Show preset details in columns
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Cost Multiplier", f"{config.estimated_cost_multiplier:.1f}x")
        with col2:
            st.metric("Processing Tokens", f"{config.max_section_tokens}")
        with col3:
            st.metric("Auto-Accept Rate", f"{config.auto_accept_threshold:.0%}")

    # Apply preset button
    if st.button("Apply Preset", type="primary"):
        apply_preset(selected_preset)
        st.success(f"Applied {selected_preset.value} preset configuration!")
        st.rerun()


def render_agent_settings() -> None:
    """Render agent configuration settings."""
    st.subheader("🤖 AI Agent Settings")

    current_config = get_merged_agent_config()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Cleaning Agent**")
        cleaning_temp = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=2.0,
            value=current_config.cleaning_temperature,
            step=0.1,
            help="Lower values = more focused, higher values = more creative",
            key="cleaning_temperature",
        )

        # Get available models from API
        available_models = get_available_openai_models()

        # Find current model index, default to o3-mini if available
        current_index = 0
        if current_config.cleaning_model in available_models:
            current_index = available_models.index(current_config.cleaning_model)
        elif "o3-mini" in str(available_models):
            # Find first o3-mini model
            current_index = next(
                (
                    i
                    for i, model in enumerate(available_models)
                    if "o3-mini" in model.lower()
                ),
                0,
            )

        cleaning_model = st.selectbox(
            "Model",
            options=available_models,
            index=current_index,
            help="AI model for cleaning transcripts",
            key="cleaning_model",
        )

    with col2:
        st.markdown("**Review Agent**")
        review_temp = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=current_config.review_temperature,
            step=0.1,
            help="Lower values recommended for consistent quality assessment",
            key="review_temperature",
        )

        # Find current review model index, default to o3-mini if available
        review_current_index = 0
        if current_config.review_model in available_models:
            review_current_index = available_models.index(current_config.review_model)
        elif "o3-mini" in str(available_models):
            # Find first o3-mini model
            review_current_index = next(
                (
                    i
                    for i, model in enumerate(available_models)
                    if "o3-mini" in model.lower()
                ),
                0,
            )

        review_model = st.selectbox(
            "Model",
            options=available_models,
            index=review_current_index,
            help="AI model for reviewing cleaned segments",
            key="review_model",
        )

    # Update configuration if values changed
    if cleaning_temp != current_config.cleaning_temperature:
        set_config_override("agents", "cleaning_temperature", cleaning_temp)
    if review_temp != current_config.review_temperature:
        set_config_override("agents", "review_temperature", review_temp)
    if cleaning_model != current_config.cleaning_model:
        set_config_override("agents", "cleaning_model", cleaning_model)
    if review_model != current_config.review_model:
        set_config_override("agents", "review_model", review_model)


def render_processing_settings() -> None:
    """Render document processing settings."""
    st.subheader("📄 Processing Settings")

    current_config = get_merged_processing_config()

    col1, col2 = st.columns(2)

    with col1:
        max_tokens = st.number_input(
            "Max Section Tokens",
            min_value=100,
            max_value=8000,
            value=current_config.max_section_tokens,
            step=100,
            help="Maximum tokens per document segment (affects cost and quality)",
            key="max_section_tokens",
        )

        min_tokens = st.number_input(
            "Min Segment Tokens",
            min_value=10,
            max_value=500,
            value=current_config.min_segment_tokens,
            step=10,
            help="Minimum tokens required for a valid segment",
            key="min_segment_tokens",
        )

    with col2:
        token_overlap = st.number_input(
            "Token Overlap",
            min_value=0,
            max_value=min(1000, max_tokens // 2),
            value=current_config.token_overlap,
            step=10,
            help="Token overlap between segments (helps maintain context)",
            key="token_overlap",
        )

        preserve_boundaries = st.checkbox(
            "Preserve Sentence Boundaries",
            value=current_config.preserve_sentence_boundaries,
            help="Avoid breaking sentences when segmenting text",
            key="preserve_sentence_boundaries",
        )

    # Update configuration if values changed
    if max_tokens != current_config.max_section_tokens:
        set_config_override("processing", "max_section_tokens", max_tokens)
    if token_overlap != current_config.token_overlap:
        set_config_override("processing", "token_overlap", token_overlap)
    if min_tokens != current_config.min_segment_tokens:
        set_config_override("processing", "min_segment_tokens", min_tokens)
    if preserve_boundaries != current_config.preserve_sentence_boundaries:
        set_config_override(
            "processing", "preserve_sentence_boundaries", preserve_boundaries
        )


def render_confidence_settings() -> None:
    """Render confidence threshold settings."""
    st.subheader("🎯 Confidence Thresholds")
    st.markdown("Configure how segments are categorized based on AI confidence scores:")

    current_config = get_merged_confidence_thresholds()

    # Auto-accept threshold (green)
    auto_accept = st.slider(
        "Auto-Accept Threshold",
        min_value=0.80,
        max_value=1.0,
        value=current_config.auto_accept_threshold,
        step=0.01,
        format="%.2f",
        help="Segments above this confidence are automatically accepted",
        key="auto_accept_threshold",
    )
    st.markdown("🟢 **Auto-Accept**: High confidence segments require no review")

    # Quick review threshold (yellow)
    quick_review = st.slider(
        "Quick Review Threshold",
        min_value=0.60,
        max_value=min(0.99, auto_accept - 0.01),
        value=min(current_config.quick_review_threshold, auto_accept - 0.01),
        step=0.01,
        format="%.2f",
        help="Segments above this confidence get quick review",
        key="quick_review_threshold",
    )
    st.markdown("🟡 **Quick Review**: Medium confidence segments need brief review")

    # Detailed review threshold (orange)
    detailed_review = st.slider(
        "Detailed Review Threshold",
        min_value=0.40,
        max_value=min(0.98, quick_review - 0.01),
        value=min(current_config.detailed_review_threshold, quick_review - 0.01),
        step=0.01,
        format="%.2f",
        help="Segments above this confidence get detailed review",
        key="detailed_review_threshold",
    )
    st.markdown("🟠 **Detailed Review**: Lower confidence segments need careful review")
    st.markdown(
        "🔴 **Flagged**: Segments below detailed threshold are flagged for attention"
    )

    # Update configuration if values changed
    if auto_accept != current_config.auto_accept_threshold:
        set_config_override(
            "confidence_thresholds", "auto_accept_threshold", auto_accept
        )
    if quick_review != current_config.quick_review_threshold:
        set_config_override(
            "confidence_thresholds", "quick_review_threshold", quick_review
        )
    if detailed_review != current_config.detailed_review_threshold:
        set_config_override(
            "confidence_thresholds", "detailed_review_threshold", detailed_review
        )


def main() -> None:
    """Main settings page."""
    st.title("⚙️ Settings")
    st.markdown(
        "Configure AI processing settings, quality presets, and confidence thresholds."
    )

    # Check if any overrides are active
    if has_config_overrides():
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("✅ Custom configuration overrides are active")
        with col2:
            if st.button("Reset to Defaults", type="secondary"):
                clear_config_overrides()
                st.success("Configuration reset to defaults!")
                st.rerun()

    # Main settings tabs
    tab1, tab2 = st.tabs(["🎯 Quality Presets", "⚙️ Advanced Settings"])

    with tab1:
        render_preset_section()

    with tab2:
        render_agent_settings()
        st.divider()
        render_processing_settings()
        st.divider()
        render_confidence_settings()

    # Footer information
    st.divider()
    st.markdown("### 💡 Tips")
    st.markdown("""
    - **Fast Preset**: Good for quick processing of drafts or informal notes
    - **Balanced Preset**: Recommended for most meeting transcripts
    - **High Quality Preset**: Use for important documents requiring maximum accuracy
    - **Temperature**: Lower values (0.0-0.3) for consistent results, higher for creativity
    - **Token Overlap**: 10-20% of max section tokens usually works well
    - **Confidence Thresholds**: Start with defaults and adjust based on your quality needs
    """)


if __name__ == "__main__":
    main()
