# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Specialist agents.

Three: the profile extractor (C1), the search-only program research agent
(C2), and the search-only alumni discovery agent (C4). Both search agents
hold `google_search` and nothing else — see spec §4.4.

Stage E was split: E1 built and tested the discovery agent without attaching
it; E2 wired it to the root alongside `save_alumni_records`, extended the
retrieval budget to cover it, and ran the first live search. The agent and
its admission gate move together — one without the other is either inert or
unsafe.
"""

from app.agents.alumni_discovery import create_alumni_discovery_agent
from app.agents.profile_extractor import create_profile_extractor_agent
from app.agents.program_research import create_program_research_agent

__all__ = [
    "create_alumni_discovery_agent",
    "create_profile_extractor_agent",
    "create_program_research_agent",
]
