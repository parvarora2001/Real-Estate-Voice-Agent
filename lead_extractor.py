import llm
from models import LeadData, LeadScore, FinancingStatus, PropertyType

class LeadExtractor:
    """Extract and score lead information from conversations"""
    
    @staticmethod
    def extract_lead_info(conversation_messages: list, call_sid: str) -> LeadData:
        """Extract structured lead data from conversation"""
        
        # Get full conversation text
        conversation_text = "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in conversation_messages
        ])
        
        # Use LLM to extract structured data
        extraction_prompt = f"""Analyze this real estate conversation and extract lead information.

Conversation:
{conversation_text}

Extract and return ONLY a JSON object with these fields (use null if not mentioned):
{{
    "name": "caller's name if mentioned",
    "property_type": "house/apartment/condo/townhouse/land/commercial/other",
    "bedrooms": number or null,
    "bathrooms": number or null,
    "min_budget": number or null,
    "max_budget": number or null,
    "preferred_locations": ["location1", "location2"],
    "timeline": "immediately/1-3 months/3-6 months/6-12 months/just browsing",
    "financing_status": "pre_approved/not_started/in_progress/cash_buyer/unknown",
    "is_first_time_buyer": true/false/null,
    "buying_signals": ["signal1", "signal2"],
    "key_requirements": ["requirement1", "requirement2"]
}}

Return ONLY the JSON, no explanation."""

        try:
            # Gemini JSON mode returns guaranteed-valid JSON
            extracted_data = llm.extract_json(extraction_prompt)

            # Create LeadData object. Normalize enum-backed fields so an unexpected
            # casing/value from the LLM (e.g. "Condo") degrades gracefully instead of
            # raising and wiping the entire lead.
            lead = LeadData(
                call_sid=call_sid,
                name=extracted_data.get('name'),
                property_type=LeadExtractor._normalize_enum(
                    extracted_data.get('property_type'), PropertyType, PropertyType.OTHER
                ),
                bedrooms=extracted_data.get('bedrooms'),
                bathrooms=extracted_data.get('bathrooms'),
                min_budget=extracted_data.get('min_budget'),
                max_budget=extracted_data.get('max_budget'),
                preferred_locations=extracted_data.get('preferred_locations', []),
                timeline=extracted_data.get('timeline'),
                financing_status=LeadExtractor._normalize_enum(
                    extracted_data.get('financing_status'), FinancingStatus, FinancingStatus.UNKNOWN
                ),
                is_first_time_buyer=extracted_data.get('is_first_time_buyer'),
                buying_signals=extracted_data.get('buying_signals', []),
                key_requirements=extracted_data.get('key_requirements', []),
                conversation_transcript=conversation_messages
            )
            
            # Score the lead
            lead.lead_score = LeadExtractor.score_lead(lead)
            
            # Generate summary
            lead.ai_summary = LeadExtractor.generate_summary(lead, conversation_text)
            
            # Determine next steps
            lead.next_steps = LeadExtractor.determine_next_steps(lead)
            
            return lead
            
        except Exception as e:
            print(f"❌ Extraction error: {e}")
            # Return minimal lead data
            return LeadData(
                call_sid=call_sid,
                conversation_transcript=conversation_messages
            )
    
    @staticmethod
    def _normalize_enum(value, enum_cls, default):
        """Coerce a raw LLM string into a valid enum member.

        Returns None for missing values (the field is Optional), an exact/case-insensitive
        match when possible, or `default` when the LLM returns something unrecognized.
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, enum_cls):
            return value
        normalized = str(value).strip().lower().replace(' ', '_').replace('-', '_')
        for member in enum_cls:
            if member.value == normalized:
                return member
        return default

    @staticmethod
    def score_lead(lead: LeadData) -> LeadScore:
        """Score lead based on qualification criteria"""
        score = 0
        
        # Budget mentioned (+2)
        if lead.min_budget or lead.max_budget:
            score += 2
        
        # Timeline (urgent = higher score)
        if lead.timeline:
            if "immediately" in lead.timeline.lower() or "asap" in lead.timeline.lower():
                score += 3
            elif "1-3 month" in lead.timeline.lower():
                score += 2
            elif "3-6 month" in lead.timeline.lower():
                score += 1
        
        # Financing status
        if lead.financing_status == FinancingStatus.PRE_APPROVED:
            score += 3
        elif lead.financing_status == FinancingStatus.CASH_BUYER:
            score += 4
        elif lead.financing_status == FinancingStatus.IN_PROGRESS:
            score += 1
        
        # Specific requirements (+1)
        if lead.bedrooms:
            score += 1
        if lead.preferred_locations:
            score += 1
        
        # Buying signals
        score += len(lead.buying_signals)
        
        # Determine score category
        if score >= 8:
            return LeadScore.HOT
        elif score >= 5:
            return LeadScore.WARM
        elif score >= 2:
            return LeadScore.COLD
        else:
            return LeadScore.UNQUALIFIED
    
    @staticmethod
    def generate_summary(lead: LeadData, conversation: str) -> str:
        """Generate human-readable summary for agents"""
        summary_parts = []
        
        # Lead score
        summary_parts.append(f"**Lead Score: {lead.lead_score.value.upper()}**")
        
        # Key info
        if lead.property_type:
            summary_parts.append(f"Looking for: {lead.property_type.value}")
        
        if lead.bedrooms:
            summary_parts.append(f"Bedrooms: {lead.bedrooms}")
        
        if lead.min_budget or lead.max_budget:
            budget_str = "Budget: "
            if lead.min_budget and lead.max_budget:
                budget_str += f"${lead.min_budget:,} - ${lead.max_budget:,}"
            elif lead.max_budget:
                budget_str += f"Up to ${lead.max_budget:,}"
            elif lead.min_budget:
                budget_str += f"Starting at ${lead.min_budget:,}"
            summary_parts.append(budget_str)
        
        if lead.preferred_locations:
            summary_parts.append(f"Locations: {', '.join(lead.preferred_locations)}")
        
        if lead.timeline:
            summary_parts.append(f"Timeline: {lead.timeline}")
        
        if lead.financing_status and lead.financing_status != FinancingStatus.UNKNOWN:
            summary_parts.append(f"Financing: {lead.financing_status.value.replace('_', ' ').title()}")
        
        # Key requirements
        if lead.key_requirements:
            summary_parts.append(f"Must-haves: {', '.join(lead.key_requirements)}")
        
        return "\n".join(summary_parts)
    
    @staticmethod
    def determine_next_steps(lead: LeadData) -> str:
        """Suggest next steps based on lead quality"""
        if lead.lead_score == LeadScore.HOT:
            return "URGENT: Call within 1 hour. Schedule showing ASAP. Send property matches immediately."
        elif lead.lead_score == LeadScore.WARM:
            return "Follow up within 24 hours. Send curated property list. Offer to schedule viewing."
        elif lead.lead_score == LeadScore.COLD:
            return "Add to nurture campaign. Send weekly property updates. Check in monthly."
        else:
            return "Add to general mailing list. Monitor for engagement."