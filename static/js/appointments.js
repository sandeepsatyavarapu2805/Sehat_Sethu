const deptSelect = document.getElementById('departmentSelect');
const doctorSelect = document.getElementById('doctorSelect');
const timeSelect = document.getElementById('timeSelect');

// Populate doctors when department changes
deptSelect.addEventListener('change', () => {
    doctorSelect.innerHTML = '<option value="">Select Doctor</option>';
    timeSelect.innerHTML = '<option value="">Select Time</option>';
    const doctors = DOCTORS[deptSelect.value] || {};
    for (const doc in doctors) {
        const option = document.createElement('option');
        option.value = doc;
        option.textContent = doc;
        doctorSelect.appendChild(option);
    }
});

// Populate times when doctor changes
doctorSelect.addEventListener('change', async () => {
    timeSelect.innerHTML = '<option value="">Select Time</option>';
    const department = deptSelect.value;
    const doctor = doctorSelect.value;
    const date = document.getElementById('apptDate').value;
    if (department && doctor && date) {
        const res = await fetch(`/available_slots/${department}/${doctor}/${date}`);
        const data = await res.json();
        const booked = data.booked_slots;
        const all = data.all_slots;
        all.forEach(time => {
            if (!booked.includes(time)) {
                const option = document.createElement('option');
                option.value = time;
                option.textContent = time;
                timeSelect.appendChild(option);
            }
        });
    }
});