import React, { useRef, useEffect, Suspense, useState, useMemo } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';
import { motion } from 'framer-motion';
import { useClaims } from '@/hooks/useClaims';

interface ClaimMarker {
  id: string;
  lat: number;
  lng: number;
  label: string;
  status: 'verified' | 'review' | 'gap';
}

const getLatLong = (locationText: string): { lat: number, lng: number } => {
  const loc = locationText.toLowerCase();
  if (loc.includes('singapore')) return { lat: 1.3521, lng: 103.8198 };
  if (loc.includes('são paulo') || loc.includes('brazil')) return { lat: -23.5505, lng: -46.6333 };
  if (loc.includes('berlin') || loc.includes('germany') || loc.includes('europe')) return { lat: 52.52, lng: 13.405 };
  if (loc.includes('tokyo') || loc.includes('japan')) return { lat: 35.6762, lng: 139.6503 };
  if (loc.includes('sydney') || loc.includes('australia')) return { lat: -33.8688, lng: 151.2093 };
  if (loc.includes('mumbai') || loc.includes('india') || loc.includes('jamshedpur')) return { lat: 19.0760, lng: 72.8777 };
  if (loc.includes('houston') || loc.includes('usa') || loc.includes('america')) return { lat: 29.7604, lng: -95.3698 };
  if (loc.includes('dubai') || loc.includes('uae')) return { lat: 25.2048, lng: 55.2708 };
  if (loc.includes('oslo')) return { lat: 59.9139, lng: 10.7522 };
  if (loc.includes('johannesburg') || loc.includes('africa')) return { lat: -26.2041, lng: 28.0473 };
  
  // Deterministic random fallback based on string hash
  let hash = 0;
  for (let i = 0; i < locationText.length; i++) hash = locationText.charCodeAt(i) + ((hash << 5) - hash);
  const lat = (hash % 180) - 90;
  const lng = ((hash >> 8) % 360) - 180;
  return { lat, lng };
};

function latLngToVector3(lat: number, lng: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lng + 180) * (Math.PI / 180);
  const x = -radius * Math.sin(phi) * Math.cos(theta);
  const y = radius * Math.cos(phi);
  const z = radius * Math.sin(phi) * Math.sin(theta);
  return new THREE.Vector3(x, y, z);
}

const getStatusColor = (status: ClaimMarker['status']) => {
  switch (status) {
    case 'verified': return '#22c55e';
    case 'review': return '#f59e0b';
    case 'gap': return '#ef4444';
  }
};

function ClaimPoint({ marker, onClick, isSelected }: { marker: ClaimMarker; onClick: () => void; isSelected: boolean }) {
  const position = latLngToVector3(marker.lat, marker.lng, 2.02);
  const color = getStatusColor(marker.status);
  const meshRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const outerRingRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  
  useFrame((state) => {
    if (meshRef.current) {
      const scale = 1 + Math.sin(state.clock.elapsedTime * 2) * 0.2;
      meshRef.current.scale.setScalar(isSelected ? scale * 1.5 : hovered ? scale * 1.3 : scale);
    }
    // Make rings face camera
    if (ringRef.current) {
      ringRef.current.lookAt(state.camera.position);
    }
    if (outerRingRef.current) {
      outerRingRef.current.lookAt(state.camera.position);
    }
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
      {/* Invisible larger click target for better hit detection */}
      <mesh 
        onClick={handleClick}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
      >
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshBasicMaterial transparent opacity={0} />
      </mesh>
      {/* Visible marker */}
      <mesh ref={meshRef}>
        <sphereGeometry args={[0.03, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {/* Glow ring */}
      <mesh ref={ringRef}>
        <ringGeometry args={[0.05, 0.07, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} />
      </mesh>
      {/* Outer pulse ring */}
      <mesh ref={outerRingRef}>
        <ringGeometry args={[0.08, 0.09, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.3} side={THREE.DoubleSide} />
      </mesh>
      {(isSelected || hovered) && (
        <Html distanceFactor={8} position={[0, 0.12, 0]} style={{ pointerEvents: 'none' }}>
          <div className="glass-panel px-3 py-1.5 text-xs whitespace-nowrap">
            <span className="text-foreground font-medium">{marker.label}</span>
          </div>
        </Html>
      )}
    </group>
  );
}

function Earth({ selectedClaim, onClaimSelect }: { selectedClaim: string | null; onClaimSelect: (id: string) => void }) {
  const earthGroupRef = useRef<THREE.Group>(null);
  const cloudsRef = useRef<THREE.Mesh>(null);
  const atmosphereRef = useRef<THREE.Mesh>(null);
  
  const { claims } = useClaims();
  
  const claimMarkers = useMemo(() => {
    return claims.map(claim => {
      const coords = getLatLong(claim.location);
      return {
        id: claim.id,
        lat: coords.lat,
        lng: coords.lng,
        label: `${claim.company}: ${claim.location}`,
        status: claim.status
      };
    }).slice(0, 50); // Performance limit to 50 pins
  }, [claims]);

  // Load actual Earth textures
  const dayTexture = useLoader(THREE.TextureLoader, '/textures/earth-daymap.jpg');
  const nightTexture = useLoader(THREE.TextureLoader, '/textures/earth-nightmap.jpg');
  const cloudTexture = useLoader(THREE.TextureLoader, '/textures/earth-clouds.jpg');
  
  useEffect(() => {
    // Configure textures for better quality
    [dayTexture, nightTexture, cloudTexture].forEach(texture => {
      texture.anisotropy = 16;
      texture.minFilter = THREE.LinearMipmapLinearFilter;
      texture.magFilter = THREE.LinearFilter;
    });
  }, [dayTexture, nightTexture, cloudTexture]);

  useFrame(() => {
    // Rotate the entire earth group (including markers) together
    if (earthGroupRef.current && !selectedClaim) {
      earthGroupRef.current.rotation.y += 0.0008;
    }
    // Clouds rotate slightly faster for parallax effect
    if (cloudsRef.current) {
      cloudsRef.current.rotation.y += 0.0004; // Relative to earth group
    }
    if (atmosphereRef.current) {
      atmosphereRef.current.rotation.y -= 0.0004; // Slight counter rotation
    }
  });

  return (
    <group>
      {/* Outer atmosphere glow - static */}
      <mesh>
        <sphereGeometry args={[2.3, 64, 64]} />
        <meshBasicMaterial 
          color="#88ccff" 
          transparent 
          opacity={0.04} 
          side={THREE.BackSide}
        />
      </mesh>
      
      {/* Inner atmosphere - subtle blue rim */}
      <mesh ref={atmosphereRef}>
        <sphereGeometry args={[2.08, 64, 64]} />
        <meshBasicMaterial 
          color="#4aa3ff" 
          transparent 
          opacity={0.08} 
          side={THREE.BackSide}
        />
      </mesh>
      
      {/* Rotating group: Earth + Markers rotate together */}
      <group ref={earthGroupRef}>
        {/* Cloud layer */}
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
        
        {/* Earth with realistic texture */}
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
        
        {/* Claim markers - now inside rotating group */}
        {claimMarkers.map((marker) => (
          <ClaimPoint
            key={marker.id}
            marker={marker}
            onClick={() => onClaimSelect(marker.id)}
            isSelected={selectedClaim === marker.id}
          />
        ))}
      </group>
    </group>
  );
}

// Loading fallback component
function EarthLoading() {
  const meshRef = useRef<THREE.Mesh>(null);
  
  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.rotation.y += 0.01;
    }
  });
  
  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[2, 32, 32]} />
      <meshBasicMaterial color="#1a3a5c" wireframe />
    </mesh>
  );
}

export const Globe = ({ onClaimSelect, selectedClaim }: { onClaimSelect: (id: string) => void; selectedClaim: string | null }) => {
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
          <Earth selectedClaim={selectedClaim} onClaimSelect={onClaimSelect} />
        </Suspense>
        
        <OrbitControls 
          enableZoom={true}
          enablePan={false}
          minDistance={3}
          maxDistance={8}
          autoRotate={!selectedClaim}
          autoRotateSpeed={0.4}
          enableDamping
          dampingFactor={0.05}
        />
      </Canvas>
    </motion.div>
  );
};

export type { ClaimMarker };
