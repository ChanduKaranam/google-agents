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

"""Cross-cutting plugins.

Spec §4.1 classifies the evidence layer as a plugin rather than an agent
because it spans every agent and tool. The three named plugins exist: the
profile audit hook from C1, plus `EvidencePlugin` and
`UntrustedContentPlugin`, which have retrieved content to police as of C2.

`NarrationIntegrityPlugin` was added by the Phase 3 audit. It is not in the
original spec inventory because the gap it closes only appeared once C3
started reporting computed numbers: everything else guards what enters
state, and this guards what leaves for the student.
"""

from app.plugins.evidence import EvidencePlugin
from app.plugins.narration_integrity import NarrationIntegrityPlugin
from app.plugins.profile_audit import ProfileAuditPlugin
from app.plugins.untrusted_content import UntrustedContentPlugin

__all__ = [
    "EvidencePlugin",
    "NarrationIntegrityPlugin",
    "ProfileAuditPlugin",
    "UntrustedContentPlugin",
]
