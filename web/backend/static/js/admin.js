// Esperar a que el DOM esté completamente cargado
document.addEventListener('DOMContentLoaded', () => {
    const { createApp } = Vue;
    
    // Funciones auxiliares para el panel de administración
    function getLogRowClass(level) {
        switch(level.toLowerCase()) {
            case 'error':
                return 'bg-red-50'
            case 'warning':
                return 'bg-yellow-50'
            case 'info':
                return 'bg-blue-50'
            default:
                return ''
        }
    }

    async function fetchRequests() {
        try {
            const response = await fetch('/api/admin/requests')
            return await response.json()
        } catch (error) {
            console.error('Error fetching requests:', error)
            return {}
        }
    }

    async function fetchActiveUsers() {
        try {
            const response = await fetch('/api/admin/users')
            return await response.json()
        } catch (error) {
            console.error('Error fetching active users:', error)
            return []
        }
    }

    async function approveRequest(id) {
        try {
            const response = await fetch(`/api/admin/approve/${id}`, {
                method: 'POST'
            })
            return response.ok
        } catch (error) {
            console.error('Error approving request:', error)
            return false
        }
    }

    async function rejectRequest(id) {
        try {
            const response = await fetch(`/api/admin/reject/${id}`, {
                method: 'POST'
            })
            return response.ok
        } catch (error) {
            console.error('Error rejecting request:', error)
            return false
        }
    }

    async function deleteUser(username) {
        try {
            const response = await fetch(`/api/admin/users/${username}`, {
                method: 'DELETE'
            })
            return response.ok
        } catch (error) {
            console.error('Error deleting user:', error)
            return false
        }
    }

    async function fetchSystemLogs() {
        try {
            const response = await fetch('/api/admin/system-status')
            const data = await response.json()
            return data.logs || []
        } catch (error) {
            console.error('Error fetching system logs:', error)
            return []
        }
    }

    const app = createApp({
        delimiters: ['[[', ']]'],
        data() {
            return {
                currentTab: 'requests',
                pendingRequests: {},
                activeUsers: [],
                clientBotLogs: [],
                managerLogs: [],
                serverLogs: [],
                updateInterval: null
            }
        },
        methods: {
            async fetchRequests() {
                this.pendingRequests = await fetchRequests()
            },
            async fetchActiveUsers() {
                this.activeUsers = await fetchActiveUsers()
            },
            async approveRequest(id) {
                if (await approveRequest(id)) {
                    await this.fetchRequests()
                }
            },
            async rejectRequest(id) {
                if (await rejectRequest(id)) {
                    await this.fetchRequests()
                }
            },
            async deleteUser(username) {
                if (confirm(`¿Estás seguro de que deseas eliminar al usuario ${username}?`)) {
                    if (await deleteUser(username)) {
                        await this.fetchActiveUsers()
                    }
                }
            },
            async fetchSystemLogs() {
                this.clientBotLogs = await fetchSystemLogs()
            },
            startAutoUpdate() {
                this.updateInterval = setInterval(() => {
                    if (this.currentTab === 'requests') {
                        this.fetchRequests()
                    } else if (this.currentTab === 'active-users') {
                        this.fetchActiveUsers()
                    } else if (this.currentTab === 'logs') {
                        this.fetchSystemLogs()
                    }
                }, 30000) // Actualizar cada 30 segundos
            }
        },
        mounted() {
            this.fetchRequests()
            this.fetchActiveUsers()
            this.fetchSystemLogs()
            this.startAutoUpdate()
        },
        beforeUnmount() {
            if (this.updateInterval) {
                clearInterval(this.updateInterval)
            }
        }
    });

    app.mount('#app');
});
