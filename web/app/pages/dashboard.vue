<template>
  <main class="min-h-screen bg-base-200">
    <!-- Hero Section with Stats -->
    <section class="relative bg-gradient-to-br from-primary/10 via-base-100 to-secondary/10">
      <div class="container mx-auto px-4 py-12">
        <!-- Header -->
        <div class="text-center mb-8">
          <h1 class="text-3xl md:text-4xl lg:text-5xl font-bold mb-3">
            Welcome Back, <b>{{ userStore.user.first_name }}</b>!
          </h1>
          <p class="text-base-content/70 text-lg">
            Here's an overview of your chemical analysis tasks
          </p>
        </div>

        <!-- Stats Cards -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-8">
          <!-- Successful Tasks -->
          <div class="card bg-base-100 shadow-lg hover:shadow-xl transition-all duration-300 border border-success/20">
            <div class="card-body items-center text-center p-6">
              <div class="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mb-3">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2"
                  stroke="currentColor" class="w-8 h-8 text-success">
                  <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                </svg>
              </div>
              <h3 class="text-sm font-medium text-base-content/70 mb-1">Successful Tasks</h3>
              <p class="text-3xl font-bold text-success">{{ totalSuccessfulTasks }}</p>
            </div>
          </div>

          <!-- Pending Tasks -->
          <div class="card bg-base-100 shadow-lg hover:shadow-xl transition-all duration-300 border border-warning/20">
            <div class="card-body items-center text-center p-6">
              <div class="w-16 h-16 rounded-full bg-warning/10 flex items-center justify-center mb-3">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2"
                  stroke="currentColor" class="w-8 h-8 text-warning">
                  <path stroke-linecap="round" stroke-linejoin="round"
                    d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
              </div>
              <h3 class="text-sm font-medium text-base-content/70 mb-1">Pending Tasks</h3>
              <p class="text-3xl font-bold text-warning">{{ totalPendingTasks }}</p>
            </div>
          </div>

          <!-- Failed Tasks -->
          <div class="card bg-base-100 shadow-lg hover:shadow-xl transition-all duration-300 border border-error/20">
            <div class="card-body items-center text-center p-6">
              <div class="w-16 h-16 rounded-full bg-error/10 flex items-center justify-center mb-3">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2"
                  stroke="currentColor" class="w-8 h-8 text-error">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </div>
              <h3 class="text-sm font-medium text-base-content/70 mb-1">Failed Tasks</h3>
              <p class="text-3xl font-bold text-error">{{ totalFailedTasks }}</p>
            </div>
          </div>

          <!-- User Chemicals -->
          <div class="card bg-base-100 shadow-lg hover:shadow-xl transition-all duration-300 border border-info/20">
            <div class="card-body items-center text-center p-6">
              <div class="w-16 h-16 rounded-full bg-info/10 flex items-center justify-center mb-3">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" fill="currentColor"
                  class="w-8 h-8 text-info">
                  <path
                    d="M256 0 34.297 128v255.999l221.702 128 221.702-128V128zm0 473.828L67.355 364.914V147.085L256 38.171l188.644 108.914v217.829h.001z" />
                  <path
                    d="M256 108.044c-81.583 0-147.956 66.372-147.956 147.956S174.416 403.957 256 403.957 403.958 337.585 403.958 256 337.583 108.044 256 108.044m0 262.854c-63.356 0-114.898-51.544-114.898-114.899S192.644 141.101 256 141.101s114.899 51.543 114.899 114.898S319.357 370.898 256 370.898" />
                </svg>
              </div>
              <h3 class="text-sm font-medium text-base-content/70 mb-1">User Chemicals</h3>
              <p class="text-3xl font-bold text-info">{{ userChemicalsStore.totalChemicals }}</p>
            </div>
          </div>
        </div>

        <!-- Quick Actions -->
        <div class="card bg-base-100 shadow-lg">
          <div class="card-body p-4 md:p-6">
            <h2 class="card-title text-xl mb-4">Quick Actions</h2>
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <!-- Draw Structure -->
              <button @click="openKetcherModal()" type="button"
                class="group btn btn-ghost bg-base-100/50 hover:bg-base-100 border border-base-300 hover:border-primary/50 hidden md:flex md:flex-col items-center justify-center gap-3 p-4 md:p-6 h-auto transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
                aria-label="Draw Chemical Structure">
                <div
                  class="w-10 h-10 md:w-12 md:h-12 flex items-center justify-center text-primary group-hover:scale-110 transition-transform duration-300">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
                    stroke="currentColor" class="w-full h-full">
                    <path stroke-linecap="round" stroke-linejoin="round"
                      d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
                  </svg>

                </div>
                <span class="font-semibold text-sm md:text-base lg:text-lg text-center">Draw Structure</span>
              </button>

              <NuxtLink to="/chemicals/search/advanced"
                class="group btn btn-ghost bg-base-100/50 hover:bg-base-100 border border-base-300 hover:border-primary/50 flex flex-col items-center justify-center gap-3 p-4 md:p-6 h-auto transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
                aria-label="Advanced Search">
                <div
                  class="w-10 h-10 md:w-12 md:h-12 flex items-center justify-center text-primary group-hover:scale-110 transition-transform duration-300">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
                    stroke="currentColor" class="w-full h-full">
                    <path stroke-linecap="round" stroke-linejoin="round"
                      d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75" />
                  </svg>
                </div>
                <span class="font-semibold text-sm md:text-base lg:text-lg text-center">Advanced Search</span>
              </NuxtLink>

              <button type="button"
                class="group btn btn-ghost bg-base-100/50 hover:bg-base-100 border border-base-300 hover:border-primary/50 flex flex-col items-center justify-center gap-3 p-4 md:p-6 h-auto transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
                @click="handleSearchAllChemicals" aria-label="Browse All Data">
                <div
                  class="w-10 h-10 md:w-12 md:h-12 flex items-center justify-center text-primary group-hover:scale-110 transition-transform duration-300">

                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
                    stroke="currentColor" class="w-full h-full">
                    <path stroke-linecap="round" stroke-linejoin="round"
                      d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
                  </svg>
                </div>
                <span class="font-semibold text-sm md:text-base lg:text-lg text-center">Browse Data</span>
              </button>

              <button type="button"
                class="group btn btn-ghost bg-base-100/50 hover:bg-base-100 border border-base-300 hover:border-primary/50 flex flex-col items-center justify-center gap-3 p-4 md:p-6 h-auto transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
                @click="openPDF2ChemicalsSubmitModal" aria-label="Submit PDF for Chemical Extraction">
                <img src="~/assets/pdf2chemicals-logo.webp" alt="" width="640" height="102"
                  class="h-auto max-h-10 md:max-h-12 w-auto max-w-full object-contain group-hover:scale-105 transition-transform duration-300" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Content Sections -->
    <div class="container mx-auto px-4 py-12 space-y-12">
      <!-- User Tasks Section -->
      <section class="space-y-6" id="user-task">
        <div class="flex items-center justify-between">
          <h2 class="text-2xl md:text-3xl font-bold">User Tasks</h2>
          <div class="badge badge-lg badge-neutral">
            {{ userTaskPagination.state.totalItems }} total
          </div>
        </div>

        <!-- Pagination Top -->
        <PaginationControls v-if="userTaskPagination.state.totalItems > 0 && userTaskPagination.getTotalPages() > 1"
          :pagination="userTaskPagination" />

        <!-- Table -->
        <div class="card bg-base-100 shadow-xl overflow-x-auto" id="user-task-table">
          <user-tasks-table />
        </div>

        <!-- Pagination Bottom -->
        <PaginationControls v-if="userTaskPagination.state.totalItems > 0 && userTaskPagination.getTotalPages() > 1"
          :pagination="userTaskPagination" />
      </section>

      <!-- User Chemicals Section -->
      <section class="space-y-6">
        <div class="flex items-center justify-between">
          <h2 class="text-2xl md:text-3xl font-bold">User Chemicals</h2>
          <div class="badge badge-lg badge-neutral">
            {{ userChemicalsPagination.state.totalItems }} total
          </div>
        </div>

        <!-- Pagination Top -->
        <PaginationControls
          v-if="userChemicalsPagination.state.totalItems > 0 && userChemicalsPagination.getTotalPages() > 1"
          :pagination="userChemicalsPagination" />

        <!-- Table -->
        <div class="card bg-base-100 shadow-xl overflow-x-auto">
          <user-chemicals-table />
        </div>

        <!-- Pagination Bottom -->
        <PaginationControls
          v-if="userChemicalsPagination.state.totalItems > 0 && userChemicalsPagination.getTotalPages() > 1"
          :pagination="userChemicalsPagination" />
      </section>
    </div>

    <!-- Modals -->
    <modal ref="ketcherModalRef">
      <ketcher-component />
    </modal>
    <modal ref="pdf2ChemicalsSubmitRef">
      <PDF2ChemicalsSubmitComponent />
    </modal>
  </main>
</template>

<script setup>
import Modal from '~/components/Modal.vue'
import UserTasksTable from '~/components/UserTasksTable.vue'
import UserChemicalsTable from '~/components/UserChemicalsTable.vue'
import PaginationControls from '~/components/PaginationControls.vue'

import { useRoute, useRouter } from 'nuxt/app'
import { defineAsyncComponent, watch } from 'vue'
import { useUserChemicalsStore } from '~/stores/userChemicals'
import { useUserTasksStore } from '~/stores/userTasks'
import { useFetchChemicalStore } from '~/stores/fetchChemicalStore'
import { usePagination } from '~/composables/usePagination'
import { useFilterStore } from '~/stores/filterStore'
import { useHistogramRangeSliderStore } from '~/stores/histogramRangeSliderStore'
import { useSortStore } from '~/stores/sortingStore'
import { useUserStore } from '~/stores/user'

const KetcherComponent = defineAsyncComponent({
  loader: () => import('~/components/KetcherComponent.vue')
})

const PDF2ChemicalsSubmitComponent = defineAsyncComponent({
  loader: () => import('~/components/PDF2ChemicalsSubmitComponent.vue')
})


const { scrollToAnchor } = useAnchorScroll()
const route = useRoute()
const router = useRouter()

// Stores
const userChemicalsStore = useUserChemicalsStore()
const userTasksStore = useUserTasksStore()
const fetchChemicalStore = useFetchChemicalStore()
const filterStore = useFilterStore()
const histogramRangeSliderStore = useHistogramRangeSliderStore()
const sortStore = useSortStore()
const userStore = useUserStore()

// Composables
const userTaskPagination = usePagination()
const userChemicalsPagination = usePagination()

// Data
const totalSuccessfulTasks = ref(0)
const totalPendingTasks = ref(0)
const totalFailedTasks = ref(0)
const isLoading = ref(true)

// Refs
const ketcherModalRef = ref(null)
const pdf2ChemicalsSubmitRef = ref(null)

// Functions
const openKetcherModal = () => {
  if (ketcherModalRef.value) {
    ketcherModalRef.value.toggleComponentModal()
  }
}

const openPDF2ChemicalsSubmitModal = () => {
  if (pdf2ChemicalsSubmitRef.value) {
    pdf2ChemicalsSubmitRef.value.toggleComponentModal()
  }
}

const handleSearchAllChemicals = () => {
  histogramRangeSliderStore.$reset()
  filterStore.$reset()
  fetchChemicalStore.$reset()
  sortStore.$reset()

  fetchChemicalStore.setType('all')
  fetchChemicalStore.setMode('summary')
  fetchChemicalStore.fetchChemicals()

  router.push('/chemicals/search')
}

async function fetchUserTasks(page) {
  userTaskPagination.setPage(page)
  await userTasksStore.fetchTasksPerUser({ page })
  userTaskPagination.setTotalItems(userTasksStore.totalTasks)
}

async function fetchUserChemicals(page) {
  userChemicalsPagination.setPage(page)
  await userChemicalsStore.fetchChemicalsPerUser({ page })
  userChemicalsPagination.setTotalItems(userChemicalsStore.totalChemicals)
}

async function loadDashboardData() {
  isLoading.value = true
  try {
    // Fetch stats
    totalSuccessfulTasks.value = await userTasksStore.getTotalSuccessfulTasks()
    totalPendingTasks.value = await userTasksStore.getTotalPendingTasks()
    totalFailedTasks.value = await userTasksStore.getTotalFailedTasks()

    // Fetch initial data
    await Promise.all([
      fetchUserTasks(1),
      fetchUserChemicals(1)
    ])
  } catch (error) {
    console.error('Error loading dashboard data:', error)
  } finally {
    isLoading.value = false
  }
}

// Watches
watch(() => userTaskPagination.state.page, (newPage) => {
  fetchUserTasks(newPage)
})

watch(() => userChemicalsPagination.state.page, (newPage) => {
  fetchUserChemicals(newPage)
})

// Lifecycle
onBeforeMount(() => {
  loadDashboardData()
})

onMounted(() => {
  if (route.hash) {

    setTimeout(() => {
      scrollToAnchor(route.hash.slice(1))
    }, 200)
  }
})

definePageMeta({
  middleware: 'auth'
})
</script>