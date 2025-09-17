/* global DOCTORS */ // This tells VSCode that DOCTORS is defined elsewhere (in HTML)

const deptSelect = document.getElementById('departmentSelect');
const doctorSelect = document.getElementById('doctorSelect');
const timeSelect = document.getElementById('timeSelect');
const appointmentForm = document.getElementById('appointmentForm');
const appointmentsList = document.getElementById('appointmentsList');
const dateInput = document.getElementById('apptDate');

// Helper: populate available times safely based on current selections
async function populateAvailableTimes() {
    if (!deptSelect || !doctorSelect || !timeSelect || !dateInput) return;
    // Reset options
    timeSelect.innerHTML = '<option value="">Select Time</option>';

    const department = deptSelect.value;
    const doctor = doctorSelect.value;
    const date = dateInput.value;

    if (department && doctor && date) {
        try {
            const res = await fetch(`/available_slots/${encodeURIComponent(department)}/${encodeURIComponent(doctor)}/${encodeURIComponent(date)}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const booked = Array.isArray(data.booked_slots) ? data.booked_slots : [];
            const all = Array.isArray(data.all_slots) ? data.all_slots : [];

            all.forEach(time => {
                if (!booked.includes(time)) {
                    const option = document.createElement('option');
                    option.value = time;
                    option.textContent = time;
                    timeSelect.appendChild(option);
                }
            });
        } catch (err) {
            console.error('Error fetching available slots:', err);
        }
    }
}

// Populate doctors when department changes
if (deptSelect && doctorSelect && timeSelect) {
    deptSelect.addEventListener('change', () => {
        doctorSelect.innerHTML = '<option value="">Select Doctor</option>';
        timeSelect.innerHTML = '<option value="">Select Time</option>';

        const doctors = (typeof DOCTORS === 'object' && DOCTORS) ? (DOCTORS[deptSelect.value] || {}) : {};
        for (const doc in doctors) {
            const option = document.createElement('option');
            option.value = doc;
            option.textContent = doc;
            doctorSelect.appendChild(option);
        }
    });
}

// Populate available times when doctor changes
if (doctorSelect && deptSelect && timeSelect && dateInput) {
    doctorSelect.addEventListener('change', async () => {
        await populateAvailableTimes();
    });
}

// Refresh times when date changes
if (dateInput && deptSelect && doctorSelect && timeSelect) {
    dateInput.addEventListener('change', async () => {
        await populateAvailableTimes();
    });
}

// Submit appointment form
if (appointmentForm && deptSelect && doctorSelect && timeSelect && dateInput) {
    appointmentForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const issueInput = appointmentForm.querySelector('input[name="issue"]');
        const appointmentData = {
            department: deptSelect.value,
            doctor: doctorSelect.value,
            date: dateInput.value,
            time: timeSelect.value,
            issue: issueInput ? (issueInput.value || '').trim() : ''
        };

        if (!appointmentData.department || !appointmentData.doctor || !appointmentData.date || !appointmentData.time) {
            alert('Please fill in all fields.');
            return;
        }

        try {
            const response = await fetch('/save_appointment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(appointmentData)
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const result = await response.json();
            if (result.status === 'success') {
                alert(result.message);
                await loadAppointments();
                appointmentForm.reset();
                await populateAvailableTimes();
            } else {
                alert(result.message || 'Failed to save appointment.');
            }
        } catch (err) {
            console.error('Error saving appointment:', err);
            alert('Failed to save appointment.');
        }
    });
}

// Load existing appointments
async function loadAppointments() {
    if (!appointmentsList) return;
    try {
        const res = await fetch('/get_appointments');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const appointments = Array.isArray(data.appointments) ? data.appointments : [];

        // Clear and render safely
        appointmentsList.textContent = '';
        if (appointments.length === 0) {
            const p = document.createElement('p');
            p.textContent = 'No appointments scheduled yet.';
            appointmentsList.appendChild(p);
            return;
        }

        appointments.forEach((appt) => {
            const item = document.createElement('div');
            item.className = 'appointment-item';

            const title = document.createElement('strong');
            title.textContent = `${appt.department || ''} - ${appt.doctor || ''}`;

            const detail = document.createElement('div');
            detail.textContent = `${appt.date || ''} | ${appt.time || ''}`;

            item.appendChild(title);
            item.appendChild(document.createElement('br'));
            item.appendChild(detail);

            appointmentsList.appendChild(item);
        });
    } catch (err) {
        console.error('Error loading appointments:', err);
    }
}

// Initial load
loadAppointments();