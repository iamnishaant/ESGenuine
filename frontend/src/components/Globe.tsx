import React, { useRef, Suspense, useState, useMemo, useEffect } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';
import { motion } from 'framer-motion';
import { MapPinned, ChevronDown } from 'lucide-react';
import { useClaims } from '@/hooks/useClaims';
import { useBackendScores } from '@/hooks/useBackendScores';
import { resolveHeadquarters } from '@/lib/companyHeadquarters';

// One marker per company, placed at its real headquarters. Clicking a marker
// surfaces that company's claims (handled by the parent).
interface CompanyMarker {
  name: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
  claimsCount: number;
  riskLevel: 'low' | 'medium' | 'high';
}

function latLngToVector3(lat: number, lng: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lng + 180) * (Math.PI / 180);
  const x = -radius * Math.sin(phi) * Math.cos(theta);
  const y = radius * Math.cos(phi);
  const z = radius * Math.sin(phi) * Math.sin(theta);
  return new THREE.Vector3(x, y, z);
}

const RISK_COLOR: Record<CompanyMarker['riskLevel'], string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#ef4444',
};

// Marker scale grows (gently, log) with the number of claims so heavier
// reporters read as bigger pins without dwarfing the smaller ones.
const sizeFactor = (claimsCount: number) =>
  Math.min(0.85 + Math.log2(claimsCount + 1) * 0.13, 2.2);

// Height of the beam that lifts a pin head clear of the globe surface.
const BEAM_H = 0.26;

// Radius of the Earth mesh. Pins anchor here and the horizon test below uses it.
const EARTH_R = 2.0;

function CompanyPin({ marker, onClick, isSelected }: { marker: CompanyMarker; onClick: () => void; isSelected: boolean }) {
  // Anchor ON the surface (r = 2.0, the Earth mesh radius) and build upward along the
  // local normal. The old pin sat at r = 2.02 with a 0.057 radius, so most of it was
  // BURIED inside the globe and the cloud layer drew at that exact radius — which is
  // why the markers were effectively invisible.
  const surface = latLngToVector3(marker.lat, marker.lng, EARTH_R);
  // Rotate local +Y to point straight out from the globe centre.
  const orientation = useMemo(() => {
    const q = new THREE.Quaternion();
    q.setFromUnitVectors(new THREE.Vector3(0, 1, 0), surface.clone().normalize());
    return q;
  }, [surface]);

  const color = RISK_COLOR[marker.riskLevel];
  const base = sizeFactor(marker.claimsCount);
  const groupRef = useRef<THREE.Group>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const outerRingRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  // Whether this pin is on the hemisphere facing the camera. drei's <Html> is a DOM
  // overlay and is NOT depth-tested against the globe, so without this every pin on
  // the FAR side still printed its company name straight through the Earth — half
  // the labels on screen belonged to markers you could not see or click.
  const [frontFacing, setFrontFacing] = useState(true);
  const worldPos = useRef(new THREE.Vector3());

  useFrame((state) => {
    if (groupRef.current) {
      const pulse = 1 + Math.sin(state.clock.elapsedTime * 2) * 0.18;
      const emphasis = isSelected ? 1.5 : hovered ? 1.25 : 1;
      groupRef.current.scale.setScalar(base * pulse * emphasis);

      // Horizon test for a sphere centred at the origin: a surface point P is visible
      // from camera C exactly when P·C > r². Cheaper and steadier than raycasting.
      groupRef.current.getWorldPosition(worldPos.current);
      const visible = worldPos.current.dot(state.camera.position) > EARTH_R * EARTH_R;
      if (visible !== frontFacing) setFrontFacing(visible);
    }
    // Rings always face the camera.
    if (ringRef.current) ringRef.current.lookAt(state.camera.position);
    if (outerRingRef.current) outerRingRef.current.lookAt(state.camera.position);
  });

  const handleClick = (e: any) => {
    e.stopPropagation();
    onClick();
  };
  const handlePointerOver = (e: any) => {
    e.stopPropagation();
    setHovered(true);
    document.body.style.cursor = 'pointer';
  };
  const handlePointerOut = () => {
    setHovered(false);
    document.body.style.cursor = 'auto';
  };

  return (
    <group position={surface} quaternion={orientation}>
      {/* Generous invisible hit target spanning the whole pin, so clicking is easy.
          Only live on the near side: an invisible mesh is still raycastable through
          the globe, so far-side pins used to steal clicks aimed at the Earth. */}
      <mesh
        position={[0, BEAM_H * 0.6, 0]}
        visible={frontFacing}
        onClick={frontFacing ? handleClick : undefined}
        onPointerOver={frontFacing ? handlePointerOver : undefined}
        onPointerOut={frontFacing ? handlePointerOut : undefined}
      >
        <cylinderGeometry args={[0.13, 0.13, BEAM_H * 1.6, 12]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>

      {/* Halo lying flat ON the surface — reads as "a site is here" even at low zoom. */}
      <mesh position={[0, 0.005, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.045, 0.075, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.55} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>

      {/* Vertical beam lifting the head clear of the terrain + cloud layer. */}
      <mesh position={[0, BEAM_H / 2, 0]}>
        <cylinderGeometry args={[0.008, 0.014, BEAM_H, 8]} />
        <meshBasicMaterial color={color} transparent opacity={0.75} depthWrite={false} />
      </mesh>

      {/* Animated head, held above the surface (scaled by claim volume + state). */}
      <group ref={groupRef} position={[0, BEAM_H, 0]}>
        <mesh>
          <sphereGeometry args={[0.042, 20, 20]} />
          <meshBasicMaterial color={color} />
        </mesh>
        <mesh ref={ringRef}>
          <ringGeometry args={[0.06, 0.085, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.75} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
        <mesh ref={outerRingRef}>
          <ringGeometry args={[0.1, 0.115, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.35} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      </group>

      {/* Company name is always legible; the full card appears on hover/selection.
          Suppressed entirely on the far side - see frontFacing above. */}
      <Html distanceFactor={9} position={[0, BEAM_H + 0.11 * base, 0]} style={{ pointerEvents: 'none' }} center>
        {!frontFacing ? null : isSelected || hovered ? (
          <div className="glass-panel px-3 py-2 text-xs whitespace-nowrap text-center">
            <div className="text-foreground font-semibold">{marker.name}</div>
            <div className="text-muted-foreground text-[11px]">{marker.city}, {marker.country}</div>
            <div className="text-[11px] mt-0.5" style={{ color }}>
              {marker.claimsCount} claim{marker.claimsCount === 1 ? '' : 's'} · {marker.riskLevel} risk
            </div>
          </div>
        ) : (
          <div
            className="px-1.5 py-0.5 rounded whitespace-nowrap text-[11px] font-medium"
            style={{ color, background: 'rgba(3,10,20,0.6)', textShadow: '0 1px 3px rgba(0,0,0,0.9)' }}
          >
            {marker.name}
          </div>
        )}
      </Html>
    </group>
  );
}

// Smallest signed delta between two angles (radians), for shortest-path lerp.
function shortestAngle(from: number, to: number): number {
  let d = (to - from) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return d;
}

function Earth({ markers, selectedCompany, onCompanySelect }: {
  markers: CompanyMarker[];
  selectedCompany: string | null;
  onCompanySelect: (name: string) => void;
}) {
  const earthGroupRef = useRef<THREE.Group>(null);
  const cloudsRef = useRef<THREE.Mesh>(null);
  const atmosphereRef = useRef<THREE.Mesh>(null);

  // Real Earth textures.
  const dayTexture = useLoader(THREE.TextureLoader, '/textures/earth-daymap.jpg');
  const nightTexture = useLoader(THREE.TextureLoader, '/textures/earth-nightmap.jpg');
  const cloudTexture = useLoader(THREE.TextureLoader, '/textures/earth-clouds.jpg');

  useEffect(() => {
    [dayTexture, nightTexture, cloudTexture].forEach((texture) => {
      texture.anisotropy = 16;
      texture.minFilter = THREE.LinearMipmapLinearFilter;
      texture.magFilter = THREE.LinearFilter;
    });
  }, [dayTexture, nightTexture, cloudTexture]);

  // The selected HQ's yaw in the globe's OWN (unrotated) frame.
  const focusAlpha = useMemo(() => {
    if (!selectedCompany) return null;
    const m = markers.find((x) => x.name === selectedCompany);
    if (!m) return null;
    const local = latLngToVector3(m.lat, m.lng, 1);
    return Math.atan2(local.z, local.x);
  }, [selectedCompany, markers]);

  // Once the flight has landed we stop steering, so the user can orbit freely
  // instead of the globe counter-rotating to keep the pin glued to the camera.
  const settled = useRef(false);
  useEffect(() => { settled.current = false; }, [focusAlpha]);

  useFrame((state) => {
    if (!earthGroupRef.current) return;
    if (focusAlpha === null) {
      // Idle: gentle auto-rotation.
      earthGroupRef.current.rotation.y += 0.0008;
    } else if (!settled.current) {
      // Rotating the group by y maps a point's local yaw `a` to the world yaw
      // `a - y`. To face the camera that world yaw must equal the camera's own
      // azimuth, so the target is `alpha - cameraAzimuth`.
      //
      // The previous formula was `PI/2 - alpha`, which only lands correctly for a
      // single longitude (alpha = PI/2) and for every other company drives the
      // marker to `alpha - (PI/2 - alpha)` - i.e. straight round to the FAR side.
      // That is the "globe spins the company away from you" bug. Deriving the
      // target from the live camera also survives the user having orbited first,
      // which a hardcoded +z assumption did not.
      const camAzimuth = Math.atan2(state.camera.position.z, state.camera.position.x);
      const delta = shortestAngle(earthGroupRef.current.rotation.y, focusAlpha - camAzimuth);
      earthGroupRef.current.rotation.y += delta * 0.08;
      if (Math.abs(delta) < 0.002) settled.current = true;
    }
    if (cloudsRef.current) cloudsRef.current.rotation.y += 0.0004;
    if (atmosphereRef.current) atmosphereRef.current.rotation.y -= 0.0004;
  });

  return (
    <group>
      {/* Outer atmosphere glow */}
      <mesh>
        <sphereGeometry args={[2.3, 64, 64]} />
        <meshBasicMaterial color="#88ccff" transparent opacity={0.04} side={THREE.BackSide} />
      </mesh>

      {/* Inner atmosphere rim */}
      <mesh ref={atmosphereRef}>
        <sphereGeometry args={[2.08, 64, 64]} />
        <meshBasicMaterial color="#4aa3ff" transparent opacity={0.08} side={THREE.BackSide} />
      </mesh>

      {/* Earth + HQ markers rotate together */}
      <group ref={earthGroupRef}>
        <mesh ref={cloudsRef}>
          <sphereGeometry args={[2.02, 64, 64]} />
          <meshStandardMaterial
            map={cloudTexture}
            transparent
            opacity={0.35}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>

        <mesh>
          <sphereGeometry args={[2, 64, 64]} />
          <meshStandardMaterial
            map={dayTexture}
            roughness={0.8}
            metalness={0.1}
            emissiveMap={nightTexture}
            emissive={new THREE.Color(0xffaa66)}
            emissiveIntensity={0.4}
          />
        </mesh>

        {markers.map((marker) => (
          <CompanyPin
            key={marker.name}
            marker={marker}
            onClick={() => onCompanySelect(marker.name)}
            isSelected={selectedCompany === marker.name}
          />
        ))}
      </group>
    </group>
  );
}

function EarthLoading() {
  const meshRef = useRef<THREE.Mesh>(null);
  useFrame(() => {
    if (meshRef.current) meshRef.current.rotation.y += 0.01;
  });
  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[2, 32, 32]} />
      <meshBasicMaterial color="#1a3a5c" wireframe />
    </mesh>
  );
}

export const Globe = ({ onCompanySelect, selectedCompany }: {
  onCompanySelect: (name: string) => void;
  selectedCompany: string | null;
}) => {
  const { companies, loading: claimsLoading } = useClaims();
  // Marker color = backend greenwashing_risk where available (same source as the
  // Integrity Audit page); groundability-derived band only as offline fallback.
  const { forCompany } = useBackendScores();
  const [pickerOpen, setPickerOpen] = useState(false);

  // One marker per company whose HQ we can resolve. Unknown HQs are skipped
  // rather than fabricated.
  const markers = useMemo<CompanyMarker[]>(() => {
    return companies
      .map((c) => {
        const hq = resolveHeadquarters(c.name);
        if (!hq) return null;
        const b = forCompany(c.name) ?? forCompany(c.id);
        const risk = b?.greenwashing_risk === 'Low' ? 'low'
          : b?.greenwashing_risk === 'High' ? 'high'
          : b?.greenwashing_risk ? 'medium'
          : (c.riskLevel as CompanyMarker['riskLevel']);
        return {
          name: c.name,
          city: hq.city,
          country: hq.country,
          lat: hq.lat,
          lng: hq.lng,
          claimsCount: c.claimsCount,
          riskLevel: risk,
        } as CompanyMarker;
      })
      .filter((m): m is CompanyMarker => m !== null);
  }, [companies, forCompany]);

  return (
    <motion.div
      className="w-full h-full relative"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.8, ease: 'easeOut' }}
    >
      {/* Company picker. A globe hides half its markers by definition, so hunting for a
          pin by dragging is a poor primary interaction — this lists every plotted company
          up front and flies the globe to the one you choose. */}
      <div className="absolute top-3 right-3 z-20 w-60">
        <button
          type="button"
          onClick={() => setPickerOpen((o) => !o)}
          className="w-full flex items-center justify-between gap-2 glass-panel px-3 py-2 text-xs text-foreground hover:bg-white/[0.06] transition-colors"
        >
          <span className="flex items-center gap-2 truncate">
            <MapPinned className="w-3.5 h-3.5 text-primary flex-shrink-0" />
            <span className="truncate">
              {selectedCompany ?? `Jump to company (${markers.length})`}
            </span>
          </span>
          <ChevronDown className={`w-3.5 h-3.5 flex-shrink-0 transition-transform ${pickerOpen ? 'rotate-180' : ''}`} />
        </button>

        {pickerOpen && (
          <div className="mt-1 glass-panel p-1 max-h-64 overflow-y-auto">
            {markers.length === 0 && (
              // Distinguish the two very different reasons this can be empty. They used
              // to look identical, which cost real debugging time: an empty globe could
              // mean "no claim data reached this component" (a data/loading bug) or
              // "claims loaded but no HQ is registered" (a registry gap). Say which.
              <div className="px-2 py-3 text-[11px] text-muted-foreground space-y-1">
                {claimsLoading ? (
                  <div>Loading claims…</div>
                ) : companies.length === 0 ? (
                  <>
                    <div className="text-warning">No claim data reached the globe.</div>
                    <div>
                      The claims table returned no companies for this component. If other
                      panels show claims, this is a data-loading bug, not a missing HQ.
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-warning">
                      {companies.length} compan{companies.length === 1 ? 'y' : 'ies'} loaded,
                      none with a known HQ.
                    </div>
                    <div className="font-mono text-[10px] break-words">
                      {companies.map((c) => c.name).join(', ')}
                    </div>
                    <div>Add them to HQ_REGISTRY in lib/companyHeadquarters.ts to plot them.</div>
                  </>
                )}
              </div>
            )}
            {markers.map((m) => (
              <button
                key={m.name}
                type="button"
                onClick={() => { onCompanySelect(m.name); setPickerOpen(false); }}
                className={`w-full text-left px-2 py-1.5 rounded hover:bg-white/[0.07] transition-colors ${
                  selectedCompany === m.name ? 'bg-white/[0.06]' : ''
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: RISK_COLOR[m.riskLevel] }} />
                  <span className="text-xs text-foreground truncate flex-1">{m.name}</span>
                  <span className="text-[10px] text-muted-foreground font-mono">{m.claimsCount}</span>
                </div>
                <div className="text-[10px] text-muted-foreground pl-4">{m.city}, {m.country}</div>
              </button>
            ))}
            {selectedCompany && (
              <button
                type="button"
                onClick={() => { onCompanySelect(selectedCompany); setPickerOpen(false); }}
                className="w-full text-left px-2 py-1.5 mt-1 rounded text-[11px] text-muted-foreground hover:bg-white/[0.07] border-t border-border/40"
              >
                Clear selection · resume rotation
              </button>
            )}
          </div>
        )}
      </div>

      <Canvas camera={{ position: [0, 0, 5], fov: 45 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 3, 5]} intensity={1.5} color="#ffffff" />
        <directionalLight position={[-5, -3, -5]} intensity={0.3} color="#4488ff" />
        <pointLight position={[10, 0, 10]} intensity={0.8} color="#ffffff" />

        <Suspense fallback={<EarthLoading />}>
          <Earth markers={markers} selectedCompany={selectedCompany} onCompanySelect={onCompanySelect} />
        </Suspense>

        <OrbitControls
          enableZoom={true}
          enablePan={false}
          minDistance={3}
          maxDistance={8}
          autoRotate={!selectedCompany}
          autoRotateSpeed={0.4}
          enableDamping
          dampingFactor={0.05}
        />
      </Canvas>
    </motion.div>
  );
};

export type { CompanyMarker };
