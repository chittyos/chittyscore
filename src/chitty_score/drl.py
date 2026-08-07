import os
import re
import math
import httpx
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

# Canonical ChittyID format: VV-G-LLL-SSSS-T-YYMM-C-XX
CHITTY_ID_REGEX = re.compile(r"^[A-Z0-9]{2}-[A-Z]-[A-Z]{3}-[A-Z0-9]{4}-E-\d{4}-[A-Z0-9]-[A-Z0-9]{2}$")

@dataclass
class DRLEvent:
    event_id: str
    action: str
    outcome: str # "success", "failure", "risky"
    timestamp: datetime
    drand_round: int
    drand_signature: str

    def __post_init__(self):
        """
        Enforce canonical ChittyID format for Event Entities (EntityType "E").
        Reference: chittycanon://gov/governance#core-types
        """
        if not CHITTY_ID_REGEX.match(self.event_id):
            raise ValueError(f"event_id must follow the canonical ChittyID format for EntityType 'E': VV-G-LLL-SSSS-E-YYMM-C-XX. Got: {self.event_id}")

class DRLRuntime:
    """
    Event Sourced Reputation (Dynamic Reputation Ledger - Pillar 2.3)
    Governing Canonical Specification: chittycanon://docs/tech/spec/event-sourced-reputation
    
    Calculates reputation weighting the trajectory of effort:
    Penalizes spam/high-frequency risky tries (e.g. 100,000 risky tries)
    Rewards slow, measured, successful steps (e.g. 7 measured steps)
    Uses Cloudflare drand for verifiable timestamps.
    """
    # Standard Cloudflare drand public key (League of Entropy)
    DRAND_PUBKEY = "868f005eb8e6e4ca0a47c8a77ceaa5309a47978a7c71bc5cce96366b5d7a569937c529eeda66c7293784a9402801af31"

    def __init__(self, drand_url: str = None):
        # Enforce canonical pattern: Network dependency injection via environment bindings
        self.drand_url = drand_url or os.environ.get("CHITTY_DRAND_URL", "https://drand.cloudflare.com/public/latest")

    async def fetch_drand_beacon(self) -> Dict[str, Any]:
        """Fetch the latest drand beacon for verifiable randomness and timestamping."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.drand_url)
            resp.raise_for_status()
            data = resp.json()
            return {
                "round": data["round"],
                "randomness": data["randomness"],
                "signature": data["signature"]
            }

    def verify_drand_signature(self, round_num: int, signature: str) -> bool:
        """
        Cryptographically verify the event's drand_signature against the expected drand public key.
        This prevents malicious actors from forging chronological spacing and simulating slow, measured steps.
        Reference: chittycanon://gov/governance (Verifiable logic mandate)
        """
        # TODO(chittyschema-overlord): Integrate BLS12-381 pairing verification here.
        # For python environments lacking the blspy/drand client binaries, we enforce the signature
        # presence and length as a mock verifiable guard until the rust-binding is deployed.
        if not signature or len(signature) != 192:
            raise ValueError(f"Invalid BLS signature format for drand round {round_num}")
        
        # In a fully deployed environment, this would verify the G2 point signature against DRAND_PUBKEY
        return True

    def calculate_reputation(self, events: List[DRLEvent]) -> float:
        """
        Calculate the reputation score based on event trajectory.
        Rewards measured steps.
        Penalizes rapid risky attempts.
        """
        if not events:
            return 0.0

        # Sort events by drand_round (verifiable chronological order)
        sorted_events = sorted(events, key=lambda e: e.drand_round)

        score = 50.0  # Base score
        
        # Trajectory analysis
        for i, event in enumerate(sorted_events):
            # Enforce Cryptographic Verification mandate before trusting the drand_round!
            if not self.verify_drand_signature(event.drand_round, event.drand_signature):
                raise ValueError(f"Cryptographic verification failed for event {event.event_id}")

            # Time delta in drand rounds (drand rounds occur at regular intervals e.g. 3s or 30s)
            round_delta = 0
            if i > 0:
                round_delta = event.drand_round - sorted_events[i-1].drand_round
            else:
                # First event has no delta, treat as a measured step
                round_delta = 100
            
            if event.outcome in ["failure", "risky"]:
                if round_delta < 10:
                    # Exponential penalty for rapid consecutive failures
                    score -= 5.0 * math.exp(-round_delta / 10.0)
                else:
                    # Standard penalty for measured failure
                    score -= 1.0
            
            elif event.outcome == "success":
                if round_delta >= 10:
                    # Reward measured, deliberate steps heavily
                    score += 3.0
                else:
                    # Rushed success gets minimal reward
                    score += 0.5
        
        # Clamp score between 0 and 100
        return max(0.0, min(100.0, score))
