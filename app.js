// Job Tracker for Spokane IT Jobs
// Uses localStorage to persist data

class JobTracker {
    constructor() {
        this.jobs = JSON.parse(localStorage.getItem('spokaneJobs')) || [];
        this.currentEditId = null;
        
        this.initEventListeners();
        this.renderJobs();
    }
    
    initEventListeners() {
        const form = document.getElementById('jobForm');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleFormSubmit();
        });
        
        document.getElementById('statusFilter').addEventListener('change', () => {
            this.renderJobs();
        });
        
        document.getElementById('companyFilter').addEventListener('input', () => {
            this.renderJobs();
        });
    }
    
    handleFormSubmit() {
        const job = {
            id: this.currentEditId || Date.now(),
            company: document.getElementById('company').value,
            title: document.getElementById('title').value,
            url: document.getElementById('url').value,
            location: document.getElementById('location').value,
            status: document.getElementById('status').value,
            salary: document.getElementById('salary').value,
            notes: document.getElementById('notes').value,
            dateAdded: this.currentEditId ? 
                this.jobs.find(j => j.id === this.currentEditId).dateAdded : 
                new Date().toISOString().split('T')[0]
        };
        
        if (this.currentEditId) {
            const index = this.jobs.findIndex(j => j.id === this.currentEditId);
            this.jobs[index] = job;
            this.currentEditId = null;
            document.querySelector('form button').textContent = 'Add Job';
        } else {
            this.jobs.unshift(job);
        }
        
        this.saveJobs();
        this.renderJobs();
        document.getElementById('jobForm').reset();
    }
    
    saveJobs() {
        localStorage.setItem('spokaneJobs', JSON.stringify(this.jobs));
    }
    
    deleteJob(id) {
        if (confirm('Are you sure you want to delete this job?')) {
            this.jobs = this.jobs.filter(job => job.id !== id);
            this.saveJobs();
            this.renderJobs();
        }
    }
    
    editJob(id) {
        const job = this.jobs.find(j => j.id === id);
        if (!job) return;
        
        document.getElementById('company').value = job.company;
        document.getElementById('title').value = job.title;
        document.getElementById('url').value = job.url;
        document.getElementById('location').value = job.location;
        document.getElementById('status').value = job.status;
        document.getElementById('salary').value = job.salary;
        document.getElementById('notes').value = job.notes;
        
        this.currentEditId = id;
        document.querySelector('form button').textContent = 'Update Job';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    renderJobs() {
        const jobsDiv = document.getElementById('jobs');
        const statusFilter = document.getElementById('statusFilter').value;
        const companyFilter = document.getElementById('companyFilter').value.toLowerCase();
        
        let filtered = this.jobs.filter(job => {
            const statusMatch = statusFilter === 'all' || job.status === statusFilter;
            const companyMatch = companyFilter === '' || 
                job.company.toLowerCase().includes(companyFilter) ||
                job.title.toLowerCase().includes(companyFilter) ||
                (job.notes && job.notes.toLowerCase().includes(companyFilter));
            return statusMatch && companyMatch;
        });
        
        if (filtered.length === 0) {
            jobsDiv.innerHTML = '<p style="color: #7f8c8d; text-align: center; padding: 20px;">No jobs to display</p>';
            return;
        }
        
        filtered.sort((a, b) => b.id - a.id); // Sort by newest first
        
        jobsDiv.innerHTML = filtered.map(job => `
            <div class="job-card">
                <div class="job-header">
                    <div>
                        <div class="job-title">${this.escapeHtml(job.title)}</div>
                        <div class="job-company">${this.escapeHtml(job.company)} | ${this.escapeHtml(job.location || 'N/A')}</div>
                    </div>
                    <span class="job-status status-${job.status}">${job.status}</span>
                </div>
                
                <div class="job-details">
                    <div><strong>Date Added:</strong> ${job.dateAdded}</div>
                    ${job.salary ? `<div><strong>Salary:</strong> ${this.escapeHtml(job.salary)}</div>` : ''}
                </div>
                
                ${job.notes ? `<div class="job-notes">${this.escapeHtml(job.notes)}</div>` : ''}
                
                <div class="job-actions">
                    ${job.url ? `<a href="${this.escapeHtml(job.url)}" target="_blank" rel="noopener" class="btn btn-url">View Job</a>` : ''}
                    <button class="btn btn-edit" onclick="jobTracker.editJob(${job.id})">Edit</button>
                    <button class="btn btn-delete" onclick="jobTracker.deleteJob(${job.id})">Delete</button>
                </div>
            </div>
        `).join('');
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.jobTracker = new JobTracker();
});
