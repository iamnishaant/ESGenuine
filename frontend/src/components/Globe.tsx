import React, { useRef, Suspense, useState, useMemo, useEffect } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';
import { motion } from 'framer-motion';
import { useClaims } from '@/hooks/useClaims';
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
  integrityScore: number;
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

function CompanyPin({ marker, onClick, isSelected }: { marker: CompanyMarker; onClick: () => void; isSelected: boolean }) {
  const position = latLngToVector3(marker.lat, marker.lng, 2.02);
  const color = RISK_COLOR[marker.riskLevel];
  const base = sizeFactor(marker.claimsCount);
  const groupRef = useRef<THREE.Group>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const outerRingRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  useFrame((state) => {
    if (groupRef.current) {
      const pulse = 1 + Math.sin(state.clock.elapsedTime * 2) * 0.18;
      const emphasis = isSelected ? 1.5 : hovered ? 1.25 : 1;
      groupRef.current.scale.setScalar(base * pulse * emphasis);
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
    <group position={position}>
      {/* Invisible larger hit target for reliable clicking */}
      <mesh onClick={handleClick} onPointerOver={handlePointerOver} onPointerOut={handlePointerOut}>
        <sphereGeometry args={[0.1, 16, 16]} />
        <meshBasicMaterial transparent opacity={0} />
      </mesh>

      {/* Animated visible marker (scaled by claim volume + state) */}
      <group ref={groupRef}>
        <mesh>
          <sphereGeometry args={[0.03, 16, 16]} />
          <meshBasicMaterial color={color} />
        </mesh>
        <mesh ref={ringRef}>
          <ringGeometry args={[0.05, 0.07, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} />
        </mesh>
        <mesh ref={outerRingRef}>
          <ringGeometry args={[0.08, 0.09, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.3} side={THREE.DoubleSide} />
        </mesh>
      </group>

      {(isSelected || hovered) && (
        <Html distanceFactor={8} position={[0, 0.14 * base, 0]} style={{ pointerEvents: 'none' }}>
          <div className="glass-panel px-3 py-2 text-xs whitespace-nowrap text-center">
            <div className="text-foreground font-semibold">{marker.name}</div>
            <div className="text-muted-foreground text-[11px]">{marker.city}, {marker.country}</div>
            <div className="text-[11px] mt-0.5" style={{ color }}>
              {marker.claimsCount} claim{marker.claimsCount === 1 ? '' : 's'} · {marker.riskLevel} risk
            </div>
          </div>
        </Html>
      )}
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

  // Yaw that brings the selected company's HQ to the front (facing the camera).
  const focusYaw = useMemo(() => {
    if (!selectedCompany) return null;
    const m = markers.find((x) => x.name === selectedCompany);
    if (!m) return null;
    const local = latLngToVector3(m.lat, m.lng, 1);
    const alpha = Math.atan2(local.z, local.x);
    return Math.PI / 2 - alpha;
  }, [selectedCompany, markers]);

  useFrame(() => {
    if (!earthGroupRef.current) return;
    if (focusYaw === null) {
      // Idle: gentle auto-rotation.
      earthGroupRef.current.rotation.y += 0.0008;
    } else {
      // Selected: ease the HQ toward the camera, then hold.
      const delta = shortestAngle(earthGroupRef.current.rotation.y, focusYaw);
      earthGroupRef.current.rotation.y += delta * 0.08;
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
  const { companies } = useClaims();

  // One marker per company whose HQ we can resolve. Unknown HQs are skipped
  // rather than fabricated.
  const markers = useMemo<CompanyMarker[]>(() => {
    return companies
      .map((c) => {
        const hq = resolveHeadquarters(c.name);
        if (!hq) return null;
        return {
          name: c.name,
          city: hq.city,
          country: hq.country,
          lat: hq.lat,
          lng: hq.lng,
          claimsCount: c.claimsCount,
          riskLevel: c.riskLevel as CompanyMarker['riskLevel'],
          integrityScore: c.integrityScore,
        } as CompanyMarker;
      })
      .filter((m): m is CompanyMarker => m !== null);
  }, [companies]);

  return (
    <motion.div
      className="w-full h-full"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.8, ease: 'easeOut' }}
    >
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
