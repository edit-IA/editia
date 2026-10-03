import React from 'react';
import {AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame} from 'remotion';

// Clipe de teste do EDIT.IA: uma palavra grande na tela (lida pelo OCR) e uma frase falada (transcrita).
export const Teste = () => {
	const f = useCurrentFrame();
	const entrada = interpolate(f, [0, 12], [0, 1], {extrapolateRight: 'clamp'});
	return (
		<AbsoluteFill style={{backgroundColor: '#111111', justifyContent: 'center', alignItems: 'center'}}>
			<div style={{opacity: entrada, color: '#FFFFFF', fontFamily: 'Arial, Helvetica, sans-serif', fontWeight: 700, fontSize: 150, letterSpacing: 4}}>
				EDITIA
			</div>
			<Audio src={staticFile('voz.wav')} />
		</AbsoluteFill>
	);
};
