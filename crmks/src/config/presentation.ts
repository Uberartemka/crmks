export const PRESTOCHI_CONFIG = {
  mapboxToken: import.meta.env.VITE_MAPBOX_TOKEN || '',

  mapStyle: 'mapbox://styles/mapbox/light-v11',

  regionsGeoJsonUrl:
    'https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_50m_admin_1_states_provinces.geojson',

  regionIdProp: 'iso_3166_2',

  phases: {
    current: ['RU-VOR', 'RU-BEL', 'RU-KRS', 'RU-LIP', 'RU-TAM'],

    phase1: [
      'RU-ROS',
      'RU-STA',
      'RU-KDA',
      'RU-VGG',
      'RU-KC',
      'RU-KB',
      'RU-ORL',
    ],

    phase2: [
      'RU-MOW', 'RU-MOS', 'RU-SPE', 'RU-LEN',
      'RU-TA', 'RU-SAM', 'RU-NIZ', 'RU-TUL', 'RU-RYA',
      'RU-YAR', 'RU-IVA', 'RU-VLA', 'RU-TVE', 'RU-KLU',
      'RU-BRY', 'RU-SMO', 'RU-KOS', 'RU-PNZ', 'RU-SAR',
      'RU-ULY', 'RU-CU', 'RU-ME', 'RU-MO', 'RU-BA',
      'RU-PER', 'RU-UD', 'RU-KIR', 'RU-ORE', 'RU-NGR',
      'RU-PSK', 'RU-VLG', 'RU-ARK', 'RU-MUR', 'RU-KR',
      'RU-KL', 'RU-KO', 'RU-DA', 'RU-IN', 'RU-SE',
      'RU-CE',
    ],
  },

  scenes: [
    { center: [100, 64], zoom: 2.4, pitch: 0, bearing: 0, activePhases: [] as string[] },
    { center: [45, 48], zoom: 4.6, pitch: 0, bearing: 0, activePhases: ['current'], duration: 3000 },
    { center: [50, 49], zoom: 3.9, pitch: 0, bearing: 0, activePhases: ['current', 'phase1'] },
    { center: [60, 56], zoom: 3.2, pitch: 0, bearing: 0, activePhases: ['current', 'phase1', 'phase2'] },
    { center: [100, 64], zoom: 2.5, pitch: 0, bearing: 0, activePhases: ['current', 'phase1', 'phase2', 'phase3'] },
  ],
} as const

export type PhaseKey = 'current' | 'phase1' | 'phase2' | 'phase3'
