const itKeywords = ['it', 'information technology', 'developer', 'software', 'engineer', 'network', 'systems', 'sysadmin', 'admin', 'support', 'help desk', 'helpdesk', 'security', 'cybersecurity', 'analyst', 'database', 'cloud', 'devops', 'infrastructure', 'desktop', 'windows', 'linux', 'aws', 'azure'];

async function loadJobs() {
    const container = document.getElementById('aggregatedJobs');
    try {
        const res = await fetch('jobs.json?' + Date.now());
        const data = await res.json();
        if (!data.jobs || data.jobs.length === 0) {
            container.innerHTML = '<p style="color: #7f8c8d;">No aggregated jobs yet. Check back later - first scrape may run on schedule.</p>';
            return;
        }
        container.innerHTML = data.jobs.slice(0, 50).map(j => `
            <div class="job-item">
                <div class="job-title"><a href="${j.url}" target="_blank" rel="noopener">${escapeHtml(j.title)}</a></div>
                <div class="job-meta">${escapeHtml(j.company)} • ${escapeHtml(j.location || 'N/A')} • ${new Date(j.posted || data.lastUpdated).toLocaleDateString()}</div>
            </div>
        `).join('');
    } catch (e) {
        container.innerHTML = '<p style="color: #7f8c8d;">Unable to load aggregated jobs.</p>';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', loadJobs);
