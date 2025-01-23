const app = Vue.createApp({
    delimiters: ['[[', ']]'],
    data() {
        return {
            currentStep: 1,
            requestId: null,
            checkStatusInterval: null,
            refundInfo: '',
            plans: [],
            plansLoaded: false,
            selectedPlan: null,
            paymentRef: '',
            paymentProof: null,
            requestStatus: null,
            ticket: null,
            error: null
        }
    },
    methods: {
        async fetchPlans() {
            try {
                console.log('Fetching plans...');
                const response = await fetch('/api/plans');
                console.log('Response:', response);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                console.log('Plans data:', data);
                
                if (Array.isArray(data)) {
                    this.plans = data;
                    this.plansLoaded = true;
                    console.log('Plans loaded:', this.plans);
                } else {
                    console.error('Invalid plans data:', data);
                    this.error = 'Error cargando los planes';
                }
            } catch (error) {
                console.error('Error fetching plans:', error);
                this.error = 'Error cargando los planes';
            }
        },
        selectPlan(plan) {
            console.log('Selecting plan:', plan);
            this.selectedPlan = plan;
        },
        nextStep() {
            this.currentStep++;
        },
        prevStep() {
            this.currentStep--;
        },
        handleFileUpload(event) {
            const file = event.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    this.paymentProof = e.target.result;
                };
                reader.readAsDataURL(file);
            }
        },
        async submitPayment() {
            try {
                const response = await fetch('/api/submit-request', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        plan: this.selectedPlan,
                        paymentRef: this.paymentRef,
                        paymentProof: this.paymentProof
                    })
                });
                const data = await response.json();
                if (response.ok) {
                    this.requestId = data.requestId;
                    this.currentStep = 3;
                    this.startStatusCheck();
                } else {
                    this.error = data.error || 'Error al enviar la solicitud';
                }
            } catch (error) {
                console.error('Error submitting payment:', error);
                this.error = 'Error al enviar la solicitud';
            }
        },
        async checkStatus() {
            try {
                const response = await fetch(`/api/check-status/${this.requestId}`);
                const data = await response.json();
                
                if (data.status === 'approved') {
                    this.requestStatus = 'approved';
                    this.ticket = data.ticket;
                    this.currentStep = 4;
                    this.stopStatusCheck();
                } else if (data.status === 'rejected') {
                    this.requestStatus = 'rejected';
                    this.currentStep = 4;
                    this.stopStatusCheck();
                }
            } catch (error) {
                console.error('Error checking status:', error);
            }
        },
        startStatusCheck() {
            this.checkStatusInterval = setInterval(this.checkStatus, 5000);
        },
        stopStatusCheck() {
            if (this.checkStatusInterval) {
                clearInterval(this.checkStatusInterval);
            }
        },
        async submitRefund() {
            try {
                const response = await fetch('/api/admin/refund', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        requestId: this.requestId,
                        username: this.ticket,
                        reason: 'Solicitud rechazada',
                        amount: this.selectedPlan.price_usd,
                        comments: this.refundInfo
                    })
                });
                
                if (response.ok) {
                    alert('Datos de devolución enviados correctamente');
                } else {
                    const data = await response.json();
                    this.error = data.error || 'Error al enviar los datos de devolución';
                }
            } catch (error) {
                console.error('Error submitting refund:', error);
                this.error = 'Error al enviar los datos de devolución';
            }
        }
    },
    mounted() {
        console.log('Component mounted');
        this.fetchPlans();
    },
    beforeUnmount() {
        this.stopStatusCheck();
    }
});

app.mount('#app');
