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

"""Deterministic function tools exposed to the root agent."""

from app.tools.alumni_tools import (
    build_alumni_query,
    get_alumni,
    rank_alumni_by_affinity,
    save_alumni_records,
)
from app.tools.comparison_tools import (
    build_comparison_matrix,
    explain_ranking_inputs,
    score_programs,
)
from app.tools.profile_tools import (
    clear_profile_fields,
    get_profile,
    normalize_gpa,
    profile_completeness,
    save_profile_fields,
)
from app.tools.program_tools import (
    build_program_query,
    get_shortlist,
    save_program_record,
)

__all__ = [
    "build_alumni_query",
    "build_comparison_matrix",
    "build_program_query",
    "clear_profile_fields",
    "explain_ranking_inputs",
    "get_alumni",
    "get_profile",
    "get_shortlist",
    "normalize_gpa",
    "profile_completeness",
    "rank_alumni_by_affinity",
    "save_alumni_records",
    "save_profile_fields",
    "save_program_record",
    "score_programs",
]
