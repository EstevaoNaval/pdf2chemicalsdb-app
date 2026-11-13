<template>
  <main>
    <header>
      <Title>Home | PDF2ChemicalsDB</Title>
    </header>

    <!-- Hero Section -->
    <section class="search_bar_background bg-scroll bg-cover bg-center relative">
      <div class="absolute inset-0 bg-gradient-to-b from-base-300/90 via-base-300/85 to-base-300/90"></div>

      <div class="relative z-10 container mx-auto px-4 py-16 md:py-24 lg:py-32">
        <!-- Hero Text -->
        <div class="max-w-4xl mx-auto text-center mb-12 space-y-6">
          <h1 class="text-4xl md:text-5xl lg:text-6xl font-bold text-primary leading-tight">
            Explore PDF2ChemicalsDB
          </h1>
          <p class="text-lg md:text-xl lg:text-2xl text-base-content/90 font-medium max-w-3xl mx-auto">
            Discover chemical data mined from literature using cutting-edge machine learning and AI technology
          </p>
        </div>

        <!-- Search Field -->
        <div class="max-w-4xl mx-auto mb-12">
          <search-field :typewriterEffect='true'></search-field>
        </div>

        <!-- Action Buttons Grid -->
        <div class="max-w-5xl mx-auto grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
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
            <span class="font-semibold text-sm md:text-base lg:text-lg text-center">Submit PDF</span>
          </button>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section class="py-16 md:py-20 lg:py-24 bg-base-100">
      <div class="container mx-auto px-4">
        <div class="text-center mb-12 md:mb-16 space-y-4">
          <h2 class="text-3xl md:text-4xl lg:text-5xl font-bold text-primary">
            Why PDF2ChemicalsDB?
          </h2>
          <p class="text-base md:text-lg lg:text-xl text-base-content/70 max-w-3xl mx-auto">
            An AI-powered database that extracts chemical data from literature, providing accurate, up-to-date
            information for researchers and chemists.
          </p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8 max-w-6xl mx-auto">
          <div
            class="card bg-base-200 hover:bg-base-300 shadow-lg hover:shadow-xl transition-all duration-300 border border-base-300">
            <div class="card-body p-6 md:p-8 space-y-4">
              <div class="w-14 h-14 rounded-lg bg-accent/10 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
                  stroke="currentColor" class="w-8 h-8 text-accent">
                  <path stroke-linecap="round" stroke-linejoin="round"
                    d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
                </svg>
              </div>
              <h3 class="text-xl md:text-2xl font-bold text-base-content">
                AI-Driven Data Mining
              </h3>
              <p class="text-base text-base-content/70 leading-relaxed">
                Automatically extracts properties, structures, and references from scientific papers using machine
                learning.
              </p>
            </div>
          </div>

          <div
            class="card bg-base-200 hover:bg-base-300 shadow-lg hover:shadow-xl transition-all duration-300 border border-base-300">
            <div class="card-body p-6 md:p-8 space-y-4">
              <div class="w-14 h-14 rounded-lg bg-accent/10 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
                  stroke="currentColor" class="w-8 h-8 text-accent">
                  <path stroke-linecap="round" stroke-linejoin="round"
                    d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
                </svg>
              </div>
              <h3 class="text-xl md:text-2xl font-bold text-base-content">
                Comprehensive Database
              </h3>
              <p class="text-base text-base-content/70 leading-relaxed">
                Access hundreds of chemicals with detailed identifiers, properties, and 3D conformations.
              </p>
            </div>
          </div>

          <div
            class="card bg-base-200 hover:bg-base-300 shadow-lg hover:shadow-xl transition-all duration-300 border border-base-300">
            <div class="card-body p-6 md:p-8 space-y-4">
              <div class="w-14 h-14 rounded-lg bg-accent/10 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
                  stroke="currentColor" class="w-8 h-8 text-accent">
                  <path stroke-linecap="round" stroke-linejoin="round"
                    d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
                </svg>
              </div>
              <h3 class="text-xl md:text-2xl font-bold text-base-content">
                User-Friendly Tools
              </h3>
              <p class="text-base text-base-content/70 leading-relaxed">
                Draw structures, advanced search, browse data, and extract chemical insights from PDFs seamlessly.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Modals -->
    <modal ref="ketcherModalRef">
      <ketcher-component></ketcher-component>
    </modal>
    <modal ref="pdf2ChemicalsSubmitRef">
      <PDF2ChemicalsSubmitComponent></PDF2ChemicalsSubmitComponent>
    </modal>
  </main>
</template>

<script setup>
import { defineAsyncComponent, ref } from 'vue';
import { useRouter } from 'vue-router'
import { useFilterStore } from '~/stores/filterStore';
import { useFetchChemicalStore } from '~/stores/fetchChemicalStore';
import { useHistogramRangeSliderStore } from '~/stores/histogramRangeSliderStore';
import { useSortStore } from '~/stores/sortingStore';
import Modal from '~/components/Modal.vue';
import SearchField from '~/components/SearchField.vue';

const KetcherComponent = defineAsyncComponent({
  loader: () => import('~/components/KetcherComponent.vue')
});

const PDF2ChemicalsSubmitComponent = defineAsyncComponent({
  loader: () => import('~/components/PDF2ChemicalsSubmitComponent.vue')
})

const router = useRouter()

const fetchChemicalStore = useFetchChemicalStore()
const histogramRangeSliderStore = useHistogramRangeSliderStore()
const filterStore = useFilterStore()
const sortStore = useSortStore()

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

const ketcherModalRef = ref(null)

const openKetcherModal = () => {
  if (ketcherModalRef.value) {
    ketcherModalRef.value.toggleComponentModal();
  }
}

const pdf2ChemicalsSubmitRef = ref(null)

const openPDF2ChemicalsSubmitModal = () => {
  if (pdf2ChemicalsSubmitRef.value) {
    pdf2ChemicalsSubmitRef.value.toggleComponentModal()
  }
}

definePageMeta({
  layout: 'default'
});
</script>

<style scoped>
.search_bar_background {
  background-image: url('~/assets/search_bar_background.webp');
}
</style>