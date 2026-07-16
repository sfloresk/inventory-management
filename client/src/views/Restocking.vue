<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <div class="budget-controls">
        <label class="budget-label" for="budget-slider">{{ t('restocking.budgetLabel') }}</label>
        <div class="budget-inputs">
          <input
            id="budget-slider"
            v-model.number="budget"
            type="range"
            min="0"
            max="25000"
            step="500"
            class="budget-slider"
          />
          <input
            v-model.number="budget"
            type="number"
            min="0"
            max="25000"
            step="500"
            class="budget-number"
          />
          <span class="budget-display">{{ currencySymbol }}{{ budget.toLocaleString() }}</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.stats.budget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ recommendation.budget.toLocaleString() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.stats.orderTotal') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ recommendation.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</div>
        </div>
        <div class="stat-card" :class="{ success: recommendation.remaining_budget > 0 }">
          <div class="stat-label">{{ t('restocking.stats.remainingBudget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ recommendation.remaining_budget.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }} ({{ recommendation.items.length }})</h3>
          <button
            class="btn-primary"
            :disabled="recommendation.items.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="submitMessage" class="success">{{ submitMessage }}</div>
        <div v-if="submitError" class="error">{{ submitError }}</div>

        <div v-if="recommendation.items.length === 0" class="empty-state">
          {{ t('restocking.emptyState') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('inventory.table.sku') }}</th>
                <th>{{ t('inventory.table.itemName') }}</th>
                <th>{{ t('inventory.table.category') }}</th>
                <th>{{ t('inventory.table.warehouse') }}</th>
                <th>{{ t('inventory.table.quantityOnHand') }}</th>
                <th>{{ t('inventory.table.reorderPoint') }}</th>
                <th>{{ t('restocking.table.restockQuantity') }}</th>
                <th>{{ t('inventory.table.unitCost') }}</th>
                <th>{{ t('restocking.table.subtotal') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendation.items" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ translateProductName(item.name) }}</td>
                <td>{{ translateCategory(item.category) }}</td>
                <td>{{ translateWarehouse(item.warehouse) }}</td>
                <td>{{ item.quantity_on_hand }}</td>
                <td>{{ item.reorder_point }}</td>
                <td><strong>{{ item.restock_quantity }}</strong></td>
                <td>{{ currencySymbol }}{{ item.unit_cost.toFixed(2) }}</td>
                <td><strong>{{ currencySymbol }}{{ item.restock_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</strong></td>
                <td>
                  <span v-if="item.trend" class="badge" :class="item.trend">{{ item.trend }}</span>
                  <span v-else>&mdash;</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName, translateWarehouse } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const loading = ref(true)
    const error = ref(null)
    const budget = ref(5000)
    const recommendation = ref({ budget: 0, total_cost: 0, remaining_budget: 0, items: [] })

    const submitting = ref(false)
    const submitMessage = ref(null)
    const submitError = ref(null)

    // Restocking respects warehouse/category filters (inventory has no time dimension)
    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    const fetchRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        recommendation.value = await api.getRestockRecommendations(budget.value, getCurrentFilters())
      } catch (err) {
        error.value = 'Failed to load restock recommendations: ' + err.message
      } finally {
        loading.value = false
      }
    }

    // Debounce budget-slider driven fetches manually (no @vueuse/core dependency in this project)
    let debounceTimer = null
    watch(budget, () => {
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        fetchRecommendations()
      }, 300)
    })

    // Warehouse/category filters apply to restocking; period/status don't (no time dimension)
    watch([selectedLocation, selectedCategory], () => {
      fetchRecommendations()
    })

    const translateCategory = (category) => {
      const categoryMap = {
        'Circuit Boards': t('categories.circuitBoards'),
        'Sensors': t('categories.sensors'),
        'Actuators': t('categories.actuators'),
        'Controllers': t('categories.controllers'),
        'Power Supplies': t('categories.powerSupplies')
      }
      return categoryMap[category] || category
    }

    const placeOrder = async () => {
      submitMessage.value = null
      submitError.value = null
      submitting.value = true
      try {
        // Map recommendation items (restock_quantity) to order line items (quantity)
        const payload = {
          budget: recommendation.value.budget,
          items: recommendation.value.items.map(item => ({
            sku: item.sku,
            name: item.name,
            category: item.category,
            warehouse: item.warehouse,
            quantity: item.restock_quantity,
            unit_cost: item.unit_cost
          }))
        }
        const order = await api.createRestockingOrder(payload)
        submitMessage.value = t('restocking.successMessage', {
          orderNumber: order.order_number,
          leadTime: order.lead_time_days
        })
      } catch (err) {
        submitError.value = t('restocking.errorMessage') + ': ' + err.message
      } finally {
        submitting.value = false
        await fetchRecommendations()
      }
    }

    onMounted(fetchRecommendations)

    return {
      t,
      loading,
      error,
      budget,
      recommendation,
      submitting,
      submitMessage,
      submitError,
      currencySymbol,
      translateProductName,
      translateWarehouse,
      translateCategory,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.25rem 1.5rem;
}

.budget-controls {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-inputs {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.budget-slider {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  accent-color: #2563eb;
  cursor: pointer;
}

.budget-number {
  width: 120px;
  padding: 0.5rem 0.625rem;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.875rem;
  color: #0f172a;
}

.budget-number:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.budget-display {
  min-width: 110px;
  text-align: right;
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.2s ease;
  white-space: nowrap;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.success {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  padding: 1rem;
  border-radius: 8px;
  margin: 1rem 0;
  font-size: 0.938rem;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}
</style>
