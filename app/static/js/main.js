/**
 * HealthGuard JavaScript Client Logic
 * Handles real-time dose logging, prescription modal workflows, and toast alerts.
 */

// Toast notification helper
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <span>${message}</span>
        <button class="alert-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    container.appendChild(alert);

    // Auto dismiss after 4.5 seconds
    setTimeout(() => {
        if (alert.parentElement) {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.4s ease';
            setTimeout(() => alert.remove(), 400);
        }
    }, 4500);
}

// 1-Click Dose Logger in Patient Portal
async function logPatientDose(prescriptionId, patientId, status) {
    try {
        const response = await fetch('/api/adherence', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prescription_id: prescriptionId,
                patient_id: patientId,
                status: status,
                notes: `Logged via Patient Portal quick action: ${status}`
            }),
        });

        const data = await response.json();

        if (!response.ok) {
            showToast(data.error || 'Failed to log dose.', 'danger');
            return;
        }

        // Update UI badge for this prescription
        const badge = document.getElementById(`statusBadge-${prescriptionId}`);
        if (badge) {
            badge.className = status === 'Taken' ? 'badge-dose badge-taken' : 'badge-dose badge-missed';
            badge.innerText = status === 'Taken' ? '✅ Taken Today' : '❌ Missed Today';
        }

        // Fetch fresh patient details to update adherence meter
        const detailRes = await fetch(`/api/patients/${patientId}`);
        if (detailRes.ok) {
            const detailData = await detailRes.json();
            const rate = detailData.adherence_statistics.rate_percentage;
            
            const rateVal = document.getElementById('adherenceRateValue');
            if (rateVal) rateVal.innerText = rate;

            const progressBar = document.getElementById('adherenceProgressBar');
            if (progressBar) {
                progressBar.style.width = `${rate}%`;
                progressBar.className = `progress-bar-fill bg-${rate >= 80 ? 'emerald' : (rate >= 60 ? 'amber' : 'rose')}`;
            }

            const takenCount = document.getElementById('countTaken');
            if (takenCount) takenCount.innerText = detailData.adherence_statistics.taken;

            const missedCount = document.getElementById('countMissed');
            if (missedCount) missedCount.innerText = detailData.adherence_statistics.missed;

            // Update ML Risk Card if present
            if (detailData.latest_risk_assessment) {
                const riskTier = document.getElementById('patientRiskTier');
                if (riskTier) {
                    const rLevel = detailData.latest_risk_assessment.risk_level;
                    riskTier.innerText = `${rLevel} Risk`;
                    riskTier.className = `stat-num text-${rLevel === 'High' ? 'rose' : (rLevel === 'Medium' ? 'amber' : 'emerald')}`;
                }

                const riskScore = document.getElementById('patientRiskScore');
                if (riskScore) {
                    riskScore.innerText = detailData.latest_risk_assessment.risk_score;
                }

                const riskRecs = document.getElementById('patientRiskRecs');
                if (riskRecs) {
                    riskRecs.innerText = detailData.latest_risk_assessment.recommendations;
                }
            }
        }

        showToast(`Intake marked as ${status}. Real-time adherence score updated.`, status === 'Taken' ? 'success' : 'warning');

    } catch (err) {
        console.error('Error logging adherence:', err);
        showToast('Network error while recording intake log.', 'danger');
    }
}

// Modal management for Add Prescription
function openAddRxModal() {
    const modal = document.getElementById('addRxModal');
    if (modal) modal.style.display = 'flex';
}

function closeAddRxModal() {
    const modal = document.getElementById('addRxModal');
    if (modal) modal.style.display = 'none';
}

function openAddRxModalForPatient(patientId, patientName) {
    const select = document.getElementById('rxPatientId');
    if (select) {
        select.value = patientId;
    }
    openAddRxModal();
}

// Submit new prescription from Doctor Portal
async function submitNewPrescription(event, doctorId) {
    event.preventDefault();
    const btn = document.getElementById('btnSubmitRx');
    if (btn) btn.disabled = true;

    const patientId = document.getElementById('rxPatientId').value;
    const medName = document.getElementById('rxMedName').value;
    const dosage = document.getElementById('rxDosage').value;
    const frequency = document.getElementById('rxFrequency').value;
    const duration = document.getElementById('rxDuration').value;
    const instructions = document.getElementById('rxInstructions').value;

    try {
        const response = await fetch('/api/prescriptions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: parseInt(patientId),
                doctor_id: doctorId,
                medication_name: medName,
                dosage: dosage,
                frequency: frequency,
                treatment_duration_days: parseInt(duration),
                instructions: instructions
            })
        });

        const data = await response.json();
        if (!response.ok) {
            showToast(data.error || 'Failed to create prescription.', 'danger');
            if (btn) btn.disabled = false;
            return;
        }

        showToast('Prescription added and patient ML risk score recalculated.', 'success');
        closeAddRxModal();
        
        // Reload after a brief pause so doctor can see the updated active medication count
        setTimeout(() => {
            window.location.reload();
        }, 800);

    } catch (err) {
        console.error('Error adding prescription:', err);
        showToast('Network error while saving prescription.', 'danger');
        if (btn) btn.disabled = false;
    }
}
