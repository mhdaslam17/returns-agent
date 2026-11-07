"""The labels used by the test set (and later by the agent's structured output).

Keep this file small. If you add or rename a label, update evals/README.md too.
"""

from enum import StrEnum


class Category(StrEnum):
    RETURN_STATUS = "return_status"          # "where is my return / pickup / refund?"
    RETURN_IN_TRIAL = "return_in_trial"      # wants to return, inside 100 nights
    OUTSIDE_TRIAL = "outside_trial"          # wants to return, after 100 nights
    DAMAGED_DEFECTIVE = "damaged_defective"  # delivery damage or warranty defect
    BILLING_DISPUTE = "billing_dispute"      # double charge, refund not received, wrong amount
    LEGAL_THREAT = "legal_threat"            # lawyer, court, consumer protection, chargeback
    OTHER = "other"                          # unclear, off-topic, or not a real customer request


class Action(StrEnum):
    AUTO_REPLY = "auto_reply"            # answer fully, no human needed
    ASK_FOR_DETAILS = "ask_for_details"  # missing order number, photos, etc.
    PREPARE_REFUND = "prepare_refund"    # refund is allowed; goes to approval if needed
    ESCALATE = "escalate"                # a person must handle it


class Tool(StrEnum):
    LOOKUP_ORDER = "lookup_order"
    CHECK_POLICY = "check_policy"
    DRAFT_REPLY = "draft_reply"
    PREPARE_REFUND = "prepare_refund"


class Language(StrEnum):
    EN = "en"
    AR = "ar"
    MIXED = "mixed"


APPROVAL_THRESHOLD_AED = 500  # policy 3.4
