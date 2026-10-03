import React from 'react';
import {Composition} from 'remotion';
import {Teste} from './Teste';

// A duração vem do setup (props.quadros), calculada a partir da fala gerada na máquina do aluno.
export const Raiz = () => (
	<Composition
		id="EditiaTeste"
		component={Teste}
		durationInFrames={300}
		fps={30}
		width={720}
		height={1280}
		defaultProps={{quadros: 300}}
		calculateMetadata={({props}) => ({durationInFrames: props.quadros})}
	/>
);
